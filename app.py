import streamlit as st
import requests
import json
import re
from datetime import datetime, timezone
from pypdf import PdfReader
from supabase import create_client

# ==================================================
# 1. SETTINGS
# ==================================================

st.set_page_config(
    page_title="SYNFLOW AI",
    page_icon="🧠",
    layout="wide"
)

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = """
أنت SYNFLOW AI، مساعد دراسي متخصص.
أجب بلغة الطالب، واشرح المعلومات بوضوح وبأسلوب مناسب لمستواه الدراسي.
استخدم العناوين والنقاط والأمثلة البسيطة.
لا تخترع معلومات علمية.
"""

LEVELS = [
    "المرحلة الابتدائية",
    "المرحلة المتوسطة",
    "المرحلة الثانوية",
    "الجامعة"
]

DEFAULTS = {
    "page": "home",
    "chat_history": [],
    "current_chat_id": None,
    "student_level": "المرحلة الثانوية",
    "quiz_questions": [],
    "quiz_submitted": False,
    "quiz_title": "",
    "quiz_index": 0,
    "quiz_score": 0,
    "quiz_answers": [],
    "quiz_saved": False,
    "supabase_client": None,
    "auth_user_email": None,
    "auth_user_id": None,
    "profile": None,
    "db_error": None
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==================================================
# 2. SUPABASE
# ==================================================

def get_supabase_client():
    if st.session_state.supabase_client is not None:
        return st.session_state.supabase_client

    try:
        url = st.secrets.get("SUPABASE_URL", "").strip()
        key = st.secrets.get("SUPABASE_KEY", "").strip()

        if not url or not key:
            return None

        client = create_client(url, key)
        st.session_state.supabase_client = client
        return client

    except Exception as e:
        st.session_state.db_error = str(e)
        return None


supabase = get_supabase_client()


def get_field(obj, field):
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def get_auth_value(response, field):
    value = get_field(response, field)

    if value is not None:
        return value

    data = get_field(response, "data")

    if data is not None:
        return get_field(data, field)

    return None


def set_logged_in_user(user, fallback_email=""):
    if user is None:
        return False

    uid = get_field(user, "id")

    if not uid:
        return False

    st.session_state.auth_user_id = str(uid)
    st.session_state.auth_user_email = (
        get_field(user, "email") or fallback_email
    )

    st.session_state.profile = None
    st.session_state.chat_history = []
    st.session_state.current_chat_id = None

    return True


def logout():
    try:
        if supabase is not None:
            supabase.auth.sign_out()
    except Exception:
        pass

    for key in [
        "auth_user_email",
        "auth_user_id",
        "profile",
        "chat_history",
        "current_chat_id"
    ]:
        st.session_state[key] = None if key != "chat_history" else []

    st.session_state.page = "home"
    st.rerun()


if supabase is not None and not st.session_state.auth_user_id:
    try:
        response = supabase.auth.get_user()
        user = get_auth_value(response, "user")

        if user is not None:
            set_logged_in_user(user)

    except Exception:
        pass


# ==================================================
# 3. DATABASE FUNCTIONS
# ==================================================

def db_select(table, columns="*", **filters):
    try:
        if supabase is None:
            return None

        query = supabase.table(table).select(columns)

        for column, value in filters.items():
            query = query.eq(column, value)

        result = query.execute()
        st.session_state.db_error = None
        return result.data or []

    except Exception as e:
        st.session_state.db_error = str(e)
        return None


def db_insert(table, values):
    try:
        if supabase is None:
            return None

        result = (
            supabase.table(table)
            .insert(values)
            .execute()
        )

        st.session_state.db_error = None
        return result.data or []

    except Exception as e:
        st.session_state.db_error = str(e)
        return None


def db_update(table, values, **filters):
    try:
        if supabase is None:
            return False

        query = supabase.table(table).update(values)

        for column, value in filters.items():
            query = query.eq(column, value)

        query.execute()
        st.session_state.db_error = None
        return True

    except Exception as e:
        st.session_state.db_error = str(e)
        return False


def current_user_id():
    return st.session_state.auth_user_id


# ==================================================
# 4. PROFILE
# ==================================================

def load_profile():
    rows = db_select(
        "profiles",
        "user_id,full_name,age,education_level",
        user_id=current_user_id()
    )

    if rows is None:
        return None

    if rows:
        profile = rows[0]
        st.session_state.profile = profile

        level = profile.get("education_level")

        if level in LEVELS:
            st.session_state.student_level = level

        return profile

    return {}


def save_profile(full_name, age, education_level):
    existing = db_select(
        "profiles",
        "user_id",
        user_id=current_user_id()
    )

    if existing is None:
        return False

    values = {
        "user_id": current_user_id(),
        "full_name": full_name.strip(),
        "age": int(age),
        "education_level": education_level,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    if existing:
        success = db_update(
            "profiles",
            values,
            user_id=current_user_id()
        )
    else:
        result = db_insert("profiles", values)
        success = result is not None and len(result) > 0

    if not success:
        return False

    st.session_state.profile = values
    st.session_state.student_level = education_level
    return True


# ==================================================
# 5. SAVED SUMMARIES
# ==================================================

def save_summary(title, source_type, source_text, summary_text):
    values = {
        "user_id": current_user_id(),
        "title": title[:200],
        "source_type": source_type,
        "source_text": source_text[:30000],
        "summary_text": summary_text[:30000]
    }

    result = db_insert("saved_summaries", values)
    return result is not None and len(result) > 0


def load_summaries():
    try:
        result = (
            supabase.table("saved_summaries")
            .select("*")
            .eq("user_id", current_user_id())
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

        st.session_state.db_error = None
        return result.data or []

    except Exception as e:
        st.session_state.db_error = str(e)
        return None


# ==================================================
# 6. QUIZ RESULTS
# ==================================================

def save_quiz_result():
    if st.session_state.quiz_saved:
        return True

    values = {
        "user_id": current_user_id(),
        "title": st.session_state.quiz_title,
        "score": int(st.session_state.quiz_score),
        "total_questions": len(st.session_state.quiz_questions),
        "questions": st.session_state.quiz_questions,
        "answers": st.session_state.quiz_answers
    }

    result = db_insert("quiz_results", values)

    if result is None or len(result) == 0:
        return False

    st.session_state.quiz_saved = True
    return True


def load_quiz_results():
    try:
        result = (
            supabase.table("quiz_results")
            .select("*")
            .eq("user_id", current_user_id())
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

        st.session_state.db_error = None
        return result.data or []

    except Exception as e:
        st.session_state.db_error = str(e)
        return None


# ==================================================
# 7. CHAT CONVERSATIONS
# ==================================================

def load_chat_list():
    try:
        result = (
            supabase.table("chat_conversations")
            .select("id,title,created_at,updated_at")
            .eq("user_id", current_user_id())
            .order("updated_at", desc=True)
            .limit(30)
            .execute()
        )

        st.session_state.db_error = None
        return result.data or []

    except Exception as e:
        st.session_state.db_error = str(e)
        return None


def create_chat(first_message):
    title = first_message.strip().replace("\n", " ")[:65]

    result = db_insert(
        "chat_conversations",
        {
            "user_id": current_user_id(),
            "title": title or "محادثة جديدة",
            "messages": []
        }
    )

    if result is None or not result:
        return None

    return result[0].get("id")


def save_chat():
    chat_id = st.session_state.current_chat_id

    if not chat_id:
        return False

    return db_update(
        "chat_conversations",
        {
            "messages": st.session_state.chat_history,
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        id=chat_id,
        user_id=current_user_id()
    )


def open_chat(chat_id):
    rows = db_select(
        "chat_conversations",
        "id,title,messages",
        id=chat_id,
        user_id=current_user_id()
    )

    if rows is None or not rows:
        return False

    st.session_state.current_chat_id = chat_id
    st.session_state.chat_history = rows[0].get("messages") or []
    return True


# ==================================================
# 8. DESIGN
# ==================================================

st.markdown("""
<style>
:root {
    --purple: #76518F;
    --purple-dark: #604078;
    --purple-light: #F4EDF8;
    --pink: #C58EAF;
    --text: #51445B;
    --muted: #91849A;
    --border: #EAE0EF;
}

[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #FFFFFF, #FCF8FD, #FFF9FC);
}

[data-testid="stHeader"] {
    background: transparent;
}

.block-container {
    max-width: 1100px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}

.synflow-header {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 17px;
    direction: ltr;
    padding: 23px;
    margin-bottom: 30px;
    border-radius: 20px;
    background: linear-gradient(110deg, #654582, #8762A7, #C38BAF);
    box-shadow: 0 10px 28px rgba(104,65,138,0.15);
}

.synflow-logo {
    width: 62px;
    height: 62px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    border-radius: 18px;
    background: #F7EFFB;
    color: #79539B;
    font-size: 35px;
}

.synflow-name {
    color: white;
    font-family: Arial, sans-serif;
    font-size: 38px;
    font-weight: 800;
    letter-spacing: 1px;
}

.syn-welcome {
    text-align: center;
    margin: 10px 0 35px;
}

.syn-welcome-title {
    color: var(--purple-dark);
    font-size: clamp(25px, 3vw, 34px);
    font-weight: 800;
    line-height: 1.4;
}

.syn-welcome-subtitle {
    color: var(--muted);
    font-size: 15px;
    margin-top: 8px;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid var(--border);
    border-radius: 18px;
    background: rgba(255,255,255,0.9);
    box-shadow: 0 5px 18px rgba(104,65,138,0.055);
    padding: 8px;
}

.syn-card-icon {
    width: 62px;
    height: 62px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 18px;
    background: #F3EAF8;
    color: #8964A7;
    font-size: 30px;
    margin: 8px auto;
}

.syn-card-icon.pink {
    background: #FCECF4;
    color: #C181AC;
}

.syn-card-title {
    color: #604577;
    font-size: 18px;
    font-weight: 750;
    margin-bottom: 5px;
}

.syn-card-description {
    color: #91849A;
    font-size: 13px;
    line-height: 1.7;
}

.stButton button,
.stFormSubmitButton button {
    min-height: 44px;
    border-radius: 12px;
    font-weight: 700;
    font-size: 14px;
    border: 1px solid #E5D7ED;
    color: #75558E;
    background: white;
    transition: 0.2s ease;
}

.stButton button:hover,
.stFormSubmitButton button:hover {
    color: #65447F;
    border-color: #CDB3DF;
    background: #F9F4FC;
}

.stButton button[kind="primary"],
.stFormSubmitButton button[kind="primary"] {
    color: white;
    border: none;
    background: linear-gradient(110deg, #78539B, #B47FAE);
    box-shadow: 0 5px 13px rgba(117,80,154,0.15);
}

[data-testid="stTextArea"] textarea,
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    border-radius: 12px;
    border-color: #E5D8ED;
    background: white;
}

[data-testid="stFileUploader"] section {
    border: 1.5px dashed #D9C3E6;
    border-radius: 15px;
    background: #FFFBFE;
}

[data-testid="stChatMessage"] {
    border: 1px solid #EEE5F3;
    border-radius: 15px;
    background: rgba(255,255,255,0.8);
}

[data-testid="stProgressBar"] > div {
    background-color: #EEE4F5;
}

[data-testid="stProgressBar"] > div > div {
    background: linear-gradient(90deg, #8963A9, #D29ABF);
}

[data-testid="stExpander"] {
    border: 1px solid #EDE2F2;
    border-radius: 13px;
    background: white;
}

h1, h2, h3 {
    color: #684982;
    font-weight: 750;
}

.syn-footer {
    text-align: center;
    color: #A99AAF;
    font-size: 12px;
    padding: 30px 0 5px;
}

/* SIDEBAR */

[data-testid="stSidebar"] {
    background: #FBF8FD;
    border-right: 1px solid #EAE0EF;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem;
}

.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    direction: ltr;
    padding: 8px 4px 18px;
    border-bottom: 1px solid #EAE0EF;
    margin-bottom: 20px;
}

.sidebar-brand-icon {
    width: 43px;
    height: 43px;
    border-radius: 13px;
    background: #EEE3F5;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 25px;
}

.sidebar-brand-name {
    color: #684982;
    font-size: 19px;
    font-weight: 850;
    letter-spacing: .3px;
}

.sidebar-section {
    color: #A092AA;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .8px;
    margin: 15px 8px 7px;
}

.sidebar-profile {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 12px 10px;
    background: white;
    border: 1px solid #EAE0EF;
    border-radius: 15px;
    margin-bottom: 18px;
}

.sidebar-avatar {
    width: 43px;
    height: 43px;
    flex-shrink: 0;
    border-radius: 50%;
    background: linear-gradient(135deg, #E8D8F1, #F7E4EF);
    color: #76518F;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 21px;
    font-weight: 800;
}

.sidebar-user-name {
    color: #604577;
    font-size: 13px;
    font-weight: 750;
    overflow-wrap: anywhere;
}

.sidebar-user-level {
    color: #998BA1;
    font-size: 11px;
    margin-top: 3px;
}

[data-testid="stSidebar"] .stButton button {
    text-align: right;
    width: 100%;
    min-height: 43px;
    border: 1px solid transparent;
    border-radius: 11px;
    background: transparent;
    color: #695779;
    font-size: 14px;
    font-weight: 600;
    box-shadow: none;
}

[data-testid="stSidebar"] .stButton button:hover {
    background: #F1E9F7;
    border-color: #E8DCEF;
    color: #684982;
}

[data-testid="stSidebar"] .stButton button[kind="primary"] {
    background: #EEE4F5;
    color: #684982;
    border: 1px solid #E2D3ED;
    box-shadow: none;
}

.sidebar-logout button {
    color: #B35F76 !important;
}

@media (max-width: 700px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .synflow-header {
        padding: 16px;
        gap: 12px;
    }

    .synflow-logo {
        width: 50px;
        height: 50px;
        font-size: 28px;
    }

    .synflow-name {
        font-size: 27px;
    }
}
</style>
""", unsafe_allow_html=True)


# ==================================================
# 9. HEADER
# ==================================================

st.markdown("""
<div class="synflow-header">
    <div class="synflow-logo">🧠</div>
    <div class="synflow-name">SYNFLOW AI</div>
</div>
""", unsafe_allow_html=True)


# ==================================================
# 10. LOGIN AND SIGNUP
# ==================================================

if not st.session_state.auth_user_id:

    st.markdown("""
    <div class="syn-welcome">
        <div class="syn-welcome-title">Welcome to SYNFLOW AI</div>
        <div class="syn-welcome-subtitle">
            سجّلي الدخول أو أنشئي حساباً للبدء
        </div>
    </div>
    """, unsafe_allow_html=True)

    if supabase is None:
        st.error("تعذر الاتصال بإعدادات Supabase. تحققي من Secrets.")

        if st.session_state.db_error:
            st.caption(str(st.session_state.db_error)[:500])

        st.stop()

    login_tab, signup_tab = st.tabs([
        "تسجيل الدخول",
        "إنشاء حساب"
    ])

    with login_tab:
        st.subheader("مرحباً بعودتك!")

        with st.form("login_form"):
            login_email = st.text_input(
                "البريد الإلكتروني",
                placeholder="example@email.com"
            )

            login_password = st.text_input(
                "كلمة المرور",
                type="password"
            )

            login_submit = st.form_submit_button(
                "تسجيل الدخول",
                type="primary",
                use_container_width=True
            )

        if login_submit:
            if not login_email.strip() or not login_password:
                st.warning("أدخلي البريد الإلكتروني وكلمة المرور.")
            else:
                try:
                    response = supabase.auth.sign_in_with_password({
                        "email": login_email.strip().lower(),
                        "password": login_password
                    })

                    user = get_auth_value(response, "user")

                    if set_logged_in_user(user, login_email.strip().lower()):
                        st.rerun()
                    else:
                        st.error("لم يتم إرجاع بيانات المستخدم.")

                except Exception as e:
                    st.error("تعذر تسجيل الدخول.")
                    st.caption(f"تفاصيل الخطأ: {str(e)[:700]}")

    with signup_tab:
        st.subheader("أنشئي حسابك")

        with st.form("signup_form"):
            signup_email = st.text_input(
                "البريد الإلكتروني",
                placeholder="example@email.com",
                key="signup_email"
            )

            signup_password = st.text_input(
                "كلمة المرور",
                type="password",
                key="signup_password"
            )

            confirm_password = st.text_input(
                "تأكيد كلمة المرور",
                type="password"
            )

            signup_submit = st.form_submit_button(
                "إنشاء حساب",
                type="primary",
                use_container_width=True
            )

        if signup_submit:
            email = signup_email.strip().lower()

            if not email:
                st.warning("أدخلي البريد الإلكتروني.")
            elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                st.warning("تحققي من صيغة البريد الإلكتروني.")
            elif len(signup_password) < 8:
                st.warning("يجب أن تتكون كلمة المرور من 8 أحرف على الأقل.")
            elif signup_password != confirm_password:
                st.warning("كلمتا المرور غير متطابقتين.")
            else:
                try:
                    response = supabase.auth.sign_up({
                        "email": email,
                        "password": signup_password
                    })

                    user = get_auth_value(response, "user")
                    session = get_auth_value(response, "session")
                    identities = (
                        get_field(user, "identities")
                        if user is not None else None
                    )

                    if user is None:
                        st.error("لم يُرجع Supabase بيانات الحساب.")
                    elif identities is not None and len(identities) == 0:
                        st.error(
                            "هذا البريد قد يكون مسجلاً مسبقاً. "
                            "جرّبي تسجيل الدخول أو استخدمي بريداً آخر."
                        )
                    elif session is not None:
                        if set_logged_in_user(user, email):
                            st.success("تم إنشاء الحساب وتسجيل الدخول!")
                            st.rerun()
                        else:
                            st.error("تم إنشاء الحساب لكن تعذر بدء جلسة الدخول.")
                    else:
                        st.success(
                            "تم إرسال طلب إنشاء الحساب. "
                            "افتحي بريدك الإلكتروني واضغطي رابط التأكيد، "
                            "ثم عودي لتسجيل الدخول."
                        )

                except Exception as e:
                    st.error("تعذر إنشاء الحساب.")
                    st.caption(f"تفاصيل الخطأ: {str(e)[:700]}")

    st.markdown(
        '<div class="syn-footer">SYNFLOW AI · Your smarter study space</div>',
        unsafe_allow_html=True
    )
    st.stop()


# ==================================================
# 11. PROFILE SETUP
# ==================================================

profile = load_profile()

if profile is None:
    st.error("تعذر قراءة ملفك من قاعدة البيانات.")

    if st.session_state.db_error:
        st.caption(str(st.session_state.db_error)[:500])

    st.stop()

if not profile:
    st.title("أكملي ملفك الدراسي")
    st.write("هذه المعلومات تساعد SYNFLOW AI على تخصيص الشرح لمستواك.")

    with st.form("first_profile_form"):
        full_name = st.text_input("الاسم")

        age = st.number_input(
            "العمر",
            min_value=5,
            max_value=100,
            value=16
        )

        education_level = st.selectbox(
            "المرحلة الدراسية",
            LEVELS
        )

        profile_submit = st.form_submit_button(
            "حفظ ومتابعة",
            type="primary",
            use_container_width=True
        )

    if profile_submit:
        if not full_name.strip():
            st.warning("اكتبي اسمك أولاً.")
        elif save_profile(full_name, age, education_level):
            st.success("تم حفظ ملفك الدراسي.")
            st.rerun()
        else:
            st.error("تعذر حفظ الملف.")

            if st.session_state.db_error:
                st.caption(str(st.session_state.db_error)[:500])

    st.stop()


# ==================================================
# 12. SIDEBAR NAVIGATION
# ==================================================

profile_name = profile.get(
    "full_name",
    st.session_state.auth_user_email or "الطالب"
)

profile_level = profile.get(
    "education_level",
    st.session_state.student_level
)

initial = profile_name.strip()[:1] if profile_name else "S"

with st.sidebar:

    st.markdown("""
    <div class="sidebar-brand">
        <div class="sidebar-brand-icon">🧠</div>
        <div class="sidebar-brand-name">SYNFLOW AI</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="sidebar-profile">
            <div class="sidebar-avatar">{initial}</div>
            <div>
                <div class="sidebar-user-name">{profile_name}</div>
                <div class="sidebar-user-level">{profile_level}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sidebar-section">القائمة الرئيسية</div>',
        unsafe_allow_html=True
    )

    navigation = [
        ("home", "⌂   الرئيسية"),
        ("profile", "♙   حسابي"),
        ("records", "▤   سجلاتي")
    ]

    for page_key, label in navigation:
        if st.button(
            label,
            key=f"sidebar_{page_key}",
            type=(
                "primary"
                if st.session_state.page == page_key
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.page = page_key
            st.rerun()

    st.markdown(
        '<div class="sidebar-section">الحساب</div>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="sidebar-logout">', unsafe_allow_html=True)

    if st.button(
        "⇥   تسجيل الخروج",
        key="sidebar_logout",
        use_container_width=True
    ):
        logout()

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div style="
            margin-top:35px;
            padding-top:15px;
            border-top:1px solid #EAE0EF;
            text-align:center;
            color:#A99AAF;
            font-size:11px;
        ">
            SYNFLOW AI<br>
            Your smarter study space
        </div>
        """,
        unsafe_allow_html=True
    )


# ==================================================
# 13. AI FUNCTIONS
# ==================================================

def call_ai(messages, temperature=0.3, max_tokens=3000):
    try:
        api_key = st.secrets.get("GROQ_API_KEY", "")

        if not api_key:
            return "لم تتم إضافة مفتاح الذكاء الاصطناعي في Secrets."

        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_completion_tokens": max_tokens
            },
            timeout=120
        )

        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        return "استغرق الطلب وقتاً طويلاً. حاولي مرة أخرى."

    except requests.exceptions.ConnectionError:
        return "تعذر الاتصال بالإنترنت."

    except requests.exceptions.HTTPError:
        try:
            error_message = response.json().get("error", {}).get("message", "")
        except Exception:
            error_message = "خطأ غير معروف"

        return f"حدث خطأ من خدمة الذكاء الاصطناعي: {error_message}"

    except Exception as e:
        return f"حدث خطأ: {str(e)}"


def ask_ai(prompt):
    return call_ai([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ])


def ai_failed(result):
    return str(result).startswith((
        "حدث خطأ",
        "تعذر",
        "استغرق",
        "لم تتم إضافة"
    ))


# ==================================================
# 14. QUIZ FUNCTIONS
# ==================================================

def extract_json(text):
    cleaned = re.sub(r"```(?:json)?|```", "", str(text)).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("لم يتم العثور على اختبار صالح.")

    return json.loads(cleaned[start:end + 1])


def create_quiz(lesson, question_type, question_count):
    prompt = f"""
أنشئ اختباراً تعليمياً باللغة العربية من المحتوى التالي فقط.

مستوى الطالب: {st.session_state.student_level}
نوع الأسئلة: {question_type}
عدد الأسئلة: {question_count}

أعد النتيجة بصيغة JSON فقط بهذا الشكل:

{{
    "questions": [
        {{
            "question": "نص السؤال",
            "options": ["الخيار الأول", "الخيار الثاني", "الخيار الثالث", "الخيار الرابع"],
            "answer": "الإجابة الصحيحة",
            "explanation": "شرح مختصر للإجابة"
        }}
    ]
}}

التعليمات:
- الاختيار من متعدد: أربعة خيارات.
- الصح والخطأ: الخيارات تكون ["صح", "خطأ"].
- الأسئلة القصيرة: اجعل options تساوي ["اكتبي إجابتك"].
- في الأسئلة القصيرة اكتب الإجابة النموذجية في answer.
- يجب أن تطابق الإجابة الصحيحة أحد الخيارات في الأسئلة الموضوعية.
- لا تضف معلومات من خارج الدرس.
- اجعل الأسئلة مناسبة للمستوى الدراسي.

الدرس:
{lesson[:18000]}
"""

    result = call_ai([
        {
            "role": "system",
            "content": "أنت مولّد اختبارات تعليمية. أعد JSON صالحاً فقط."
        },
        {"role": "user", "content": prompt}
    ])

    if ai_failed(result):
        raise RuntimeError(result)

    data = extract_json(result)
    questions = data.get("questions", [])

    if not isinstance(questions, list) or not questions:
        raise ValueError("لم يتم إنشاء أسئلة صالحة.")

    valid_questions = []

    for question in questions[:question_count]:
        if not isinstance(question, dict):
            continue

        if not question.get("question") or not question.get("answer"):
            continue

        if not isinstance(question.get("options"), list):
            question["options"] = ["اكتبي إجابتك"]

        if not question.get("explanation"):
            question["explanation"] = ""

        valid_questions.append(question)

    if not valid_questions:
        raise ValueError("الأسئلة التي تم إنشاؤها غير مكتملة.")

    return valid_questions


def start_quiz(questions, title):
    st.session_state.quiz_questions = questions
    st.session_state.quiz_title = title
    st.session_state.quiz_index = 0
    st.session_state.quiz_score = 0
    st.session_state.quiz_answers = []
    st.session_state.quiz_submitted = False
    st.session_state.quiz_saved = False
    st.session_state.page = "quiz"


def render_quiz():
    questions = st.session_state.quiz_questions
    total = len(questions)
    index = st.session_state.quiz_index

    if index < total:
        question = questions[index]

        st.title(st.session_state.quiz_title)
        st.progress((index + 1) / total)
        st.caption(f"السؤال {index + 1} من {total}")

        st.markdown("### " + question["question"])

        options = question.get("options", [])

        if options == ["اكتبي إجابتك"]:
            answer = st.text_area(
                "اكتبي إجابتك:",
                key=f"short_{index}"
            )
        else:
            answer = st.radio(
                "اختاري الإجابة:",
                options,
                index=None,
                key=f"answer_{index}"
            )

        if not st.session_state.quiz_submitted:
            if st.button(
                "تأكيد الإجابة",
                type="primary",
                use_container_width=True
            ):
                if answer is None or not str(answer).strip():
                    st.warning("اختاري أو اكتبي إجابة أولاً.")
                else:
                    correct = str(question.get("answer", "")).strip()

                    is_correct = (
                        str(answer).strip().casefold()
                        == correct.casefold()
                    )

                    if is_correct:
                        st.session_state.quiz_score += 1

                    st.session_state.quiz_answers.append({
                        "question": question["question"],
                        "given": answer,
                        "correct": correct,
                        "explanation": question.get("explanation", ""),
                        "is_correct": is_correct
                    })

                    st.session_state.quiz_submitted = True
                    st.rerun()

        else:
            if st.session_state.quiz_answers:
                last = st.session_state.quiz_answers[-1]

                if last["is_correct"]:
                    st.success("إجابة صحيحة!")
                else:
                    st.error("الإجابة النموذجية: " + last["correct"])

                if last["explanation"]:
                    st.info(last["explanation"])

            if st.button(
                "السؤال التالي ←",
                type="primary",
                use_container_width=True
            ):
                st.session_state.quiz_index += 1
                st.session_state.quiz_submitted = False
                st.rerun()

    else:
        score = st.session_state.quiz_score

        st.title("انتهى الاختبار!")

        st.markdown(
            f"<h1 style='text-align:center;color:#875AA8;'>"
            f"{score} / {total}</h1>",
            unsafe_allow_html=True
        )

        st.progress(score / total if total else 0)

        if not st.session_state.quiz_saved:
            if save_quiz_result():
                st.success("تم حفظ نتيجتك في حسابك.")
            else:
                st.warning("انتهى الاختبار، لكن تعذر حفظ النتيجة.")

                if st.session_state.db_error:
                    st.caption(str(st.session_state.db_error)[:500])

        for i, item in enumerate(st.session_state.quiz_answers, 1):
            with st.expander(f"السؤال {i}"):
                st.write(item["question"])
                st.write("إجابتك: " + str(item["given"]))
                st.write("الإجابة الصحيحة: " + item["correct"])

                if item["explanation"]:
                    st.caption(item["explanation"])

        if st.button(
            "العودة للرئيسية",
            type="primary",
            use_container_width=True
        ):
            st.session_state.page = "home"
            st.session_state.quiz_questions = []
            st.session_state.quiz_answers = []
            st.session_state.quiz_submitted = False
            st.session_state.quiz_saved = False
            st.rerun()


# ==================================================
# 15. BACK BUTTON
# ==================================================

def back_button():
    if st.button("← العودة للرئيسية"):
        st.session_state.page = "home"
        st.rerun()


# ==================================================
# 16. HOME PAGE - FOUR STUDY TOOLS
# ==================================================

if st.session_state.page == "home":

    st.markdown("""
    <div class="syn-welcome">
        <div class="syn-welcome-title">
            Learn smarter. Grow brighter.
        </div>
        <div class="syn-welcome-subtitle">
            مساحتك الذكية للتعلم والفهم والتطور
        </div>
    </div>
    """, unsafe_allow_html=True)

    cards = [
        {
            "icon": "📄",
            "title": "تلخيص النصوص",
            "description": "حوّلي دروسك إلى ملخصات واضحة ومنظمة.",
            "page": "text",
            "color": ""
        },
        {
            "icon": "📑",
            "title": "تلخيص ملفات PDF",
            "description": "استخرجي أهم المعلومات من ملفاتك الدراسية.",
            "page": "pdf",
            "color": "pink"
        },
        {
            "icon": "✓",
            "title": "الاختبارات الذكية",
            "description": "اختبري معلوماتك وتابعي تقدمك خطوة بخطوة.",
            "page": "quiz",
            "color": "pink"
        },
        {
            "icon": "✧",
            "title": "المساعد الذكي",
            "description": "اسألي وناقشي واحصلي على شرح يناسب مستواك.",
            "page": "chat",
            "color": ""
        }
    ]

    col1, col2 = st.columns(2, gap="large")

    for i, card in enumerate(cards):
        col = col1 if i % 2 == 0 else col2

        with col:
            with st.container(border=True):
                icon_col, content_col = st.columns([1, 3])

                with icon_col:
                    st.markdown(
                        f"""
                        <div class="syn-card-icon {card['color']}">
                            {card['icon']}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                with content_col:
                    st.markdown(
                        f"<div class='syn-card-title'>{card['title']}</div>",
                        unsafe_allow_html=True
                    )

                    st.markdown(
                        f"<div class='syn-card-description'>{card['description']}</div>",
                        unsafe_allow_html=True
                    )

                if st.button(
                    "فتح الأداة  ←",
                    key=f"open_{card['page']}",
                    use_container_width=True
                ):
                    st.session_state.page = card["page"]
                    st.rerun()

    st.markdown(
        '<div class="syn-footer">SYNFLOW AI · Your smarter study space</div>',
        unsafe_allow_html=True
    )


# ==================================================
# 17. PROFILE PAGE
# ==================================================

elif st.session_state.page == "profile":

    back_button()
    st.title("ملفي الدراسي")

    profile_data = st.session_state.profile or {}

    with st.form("edit_profile_form"):
        full_name = st.text_input(
            "الاسم",
            value=profile_data.get("full_name", "")
        )

        age = st.number_input(
            "العمر",
            min_value=5,
            max_value=100,
            value=int(profile_data.get("age") or 16)
        )

        current_level = profile_data.get(
            "education_level",
            "المرحلة الثانوية"
        )

        level_index = (
            LEVELS.index(current_level)
            if current_level in LEVELS else 2
        )

        education_level = st.selectbox(
            "المرحلة الدراسية",
            LEVELS,
            index=level_index
        )

        profile_submit = st.form_submit_button(
            "حفظ التعديلات",
            type="primary",
            use_container_width=True
        )

    if profile_submit:
        if not full_name.strip():
            st.warning("اكتبي اسمك.")
        elif save_profile(full_name, age, education_level):
            st.success("تم تحديث ملفك.")
            st.rerun()
        else:
            st.error("تعذر حفظ التعديلات.")

            if st.session_state.db_error:
                st.caption(str(st.session_state.db_error)[:500])


# ==================================================
# 18. TEXT SUMMARIZER
# ==================================================

elif st.session_state.page == "text":

    back_button()

    st.title("تلخيص النصوص")
    st.caption("حوّلي محتوى دروسك إلى ملخص واضح ومنظم.")

    lesson = st.text_area(
        "الصقي الدرس هنا:",
        height=230
    )

    summary_type = st.selectbox(
        "نوع الملخص",
        ["ملخص قصير", "ملخص تفصيلي", "أهم النقاط"]
    )

    if st.button(
        "تلخيص الدرس",
        type="primary",
        use_container_width=True
    ):
        if not lesson.strip():
            st.warning("الصقي الدرس أولاً.")
        else:
            prompt = f"""
لخص الدرس باللغة العربية.
مستوى الطالب: {st.session_state.student_level}
نوع الملخص: {summary_type}

استخدم عناوين ونقاط واضحة.
حافظ على المعلومات العلمية.
لا تضف معلومات غير موجودة في الدرس.

الدرس:
{lesson[:25000]}
"""

            with st.spinner("جاري تلخيص الدرس..."):
                result = ask_ai(prompt)

            st.markdown("### الملخص")
            st.markdown(result)

            if not ai_failed(result):
                if save_summary(
                    "ملخص نص دراسي",
                    "text",
                    lesson,
                    result
                ):
                    st.success("تم حفظ الملخص في سجلاتك.")
                else:
                    st.warning("ظهر الملخص، لكن تعذر حفظه.")

                    if st.session_state.db_error:
                        st.caption(str(st.session_state.db_error)[:500])


# ==================================================
# 19. PDF SUMMARIZER
# ==================================================

elif st.session_state.page == "pdf":

    back_button()

    st.title("تلخيص ملفات PDF")
    st.caption("ارفعي ملفك واحصلي على ملخص لأهم محتوياته.")

    pdf_file = st.file_uploader(
        "ارفعي ملف PDF",
        type=["pdf"]
    )

    summary_type = st.selectbox(
        "نوع الملخص",
        ["ملخص قصير", "ملخص تفصيلي", "أهم النقاط"],
        key="pdf_summary"
    )

    if st.button(
        "ابدئي تلخيص الملف",
        type="primary",
        use_container_width=True
    ):
        if pdf_file is None:
            st.warning("ارفعي ملف PDF أولاً.")
        else:
            try:
                reader = PdfReader(pdf_file)

                pdf_text = "\n".join(
                    page.extract_text() or ""
                    for page in reader.pages
                )

                if not pdf_text.strip():
                    st.warning(
                        "لم يتم العثور على نص. "
                        "قد يكون الملف مصوراً ويحتاج إلى OCR."
                    )
                else:
                    prompt = f"""
لخص محتوى ملف PDF باللغة العربية.
مستوى الطالب: {st.session_state.student_level}
نوع الملخص: {summary_type}

استخدم عناوين ونقاط واضحة.
حافظ على المعلومات المهمة.
لا تضف معلومات من خارج الملف.

المحتوى:
{pdf_text[:25000]}
"""

                    with st.spinner("جاري قراءة وتلخيص الملف..."):
                        result = ask_ai(prompt)

                    st.markdown("### ملخص الملف")
                    st.markdown(result)

                    if not ai_failed(result):
                        if save_summary(
                            f"ملخص PDF: {pdf_file.name}",
                            "pdf",
                            pdf_text,
                            result
                        ):
                            st.success("تم حفظ الملخص في سجلاتك.")
                        else:
                            st.warning("ظهر الملخص، لكن تعذر حفظه.")

                            if st.session_state.db_error:
                                st.caption(str(st.session_state.db_error)[:500])

            except Exception as e:
                st.error(f"تعذر قراءة الملف: {str(e)}")


# ==================================================
# 20. SMART QUIZZES
# ==================================================

elif st.session_state.page == "quiz":

    back_button()

    if st.session_state.quiz_questions:
        render_quiz()

    else:
        st.title("الاختبارات الذكية")
        st.caption("أنشئي اختباراً تفاعلياً من درسك.")

        lesson = st.text_area(
            "الصقي الدرس الذي تريدين إنشاء اختبار منه:",
            height=220
        )

        question_type = st.selectbox(
            "نوع الاختبار",
            ["اختيار من متعدد", "صح أو خطأ", "أسئلة قصيرة"]
        )

        question_count = st.selectbox(
            "عدد الأسئلة",
            [5, 10, 15, 20]
        )

        if st.button(
            "إنشاء الاختبار",
            type="primary",
            use_container_width=True
        ):
            if not lesson.strip():
                st.warning("الصقي الدرس أولاً.")
            else:
                try:
                    with st.spinner("جاري إنشاء الاختبار..."):
                        questions = create_quiz(
                            lesson,
                            question_type,
                            question_count
                        )

                    start_quiz(questions, "اختبار الدرس")
                    st.rerun()

                except Exception as e:
                    st.error(f"تعذر إنشاء الاختبار: {str(e)}")


# ==================================================
# 21. AI STUDY ASSISTANT
# ==================================================

elif st.session_state.page == "chat":

    back_button()

    st.title("المساعد الذكي")
    st.caption("اسألي عن دروسك واحصلي على شرح يناسب مستواك الدراسي.")

    level = st.selectbox(
        "اختاري مستواك الدراسي:",
        LEVELS,
        key="student_level"
    )

    chat_col, new_col = st.columns([3, 1])

    with chat_col:
        st.caption("محادثاتك المحفوظة")

    with new_col:
        if st.button("＋ محادثة جديدة", use_container_width=True):
            st.session_state.current_chat_id = None
            st.session_state.chat_history = []
            st.rerun()

    saved_chats = load_chat_list()

    if saved_chats is None:
        st.error("تعذر تحميل محادثاتك.")

        if st.session_state.db_error:
            st.caption(str(st.session_state.db_error)[:500])

    elif saved_chats:
        with st.expander("فتح محادثة سابقة"):
            for chat in saved_chats:
                if st.button(
                    chat.get("title") or "محادثة",
                    key=f"open_chat_{chat.get('id')}",
                    use_container_width=True
                ):
                    if open_chat(chat.get("id")):
                        st.rerun()
                    else:
                        st.error("تعذر فتح المحادثة.")

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_message = st.chat_input("اكتبي سؤالك هنا...")

    if user_message:
        if not st.session_state.current_chat_id:
            new_chat_id = create_chat(user_message)

            if not new_chat_id:
                st.error("تعذر إنشاء محادثة في قاعدة البيانات.")

                if st.session_state.db_error:
                    st.caption(str(st.session_state.db_error)[:500])

                st.stop()

            st.session_state.current_chat_id = new_chat_id

        st.session_state.chat_history.append({
            "role": "user",
            "content": user_message
        })

        messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + f" مستوى الطالب: {level}. "
                    + "اجعل الشرح مناسباً لهذا المستوى."
                )
            }
        ] + st.session_state.chat_history[-20:]

        with st.spinner("المساعد يفكر..."):
            reply = call_ai(
                messages,
                temperature=0.4,
                max_tokens=2500
            )

        st.session_state.chat_history.append({
            "role": "assistant",
            "content": reply
        })

        if save_chat():
            st.rerun()
        else:
            st.warning("ظهرت الإجابة، لكن تعذر حفظ المحادثة.")

            if st.session_state.db_error:
                st.caption(str(st.session_state.db_error)[:500])

    if st.session_state.chat_history:
        st.divider()

        if st.button(
            "اختبرني من محادثتنا",
            type="primary",
            use_container_width=True
        ):
            conversation = "\n".join(
                (
                    "الطالب: " if m["role"] == "user"
                    else "المساعد: "
                ) + m["content"]
                for m in st.session_state.chat_history
            )

            try:
                with st.spinner("جاري إعداد الاختبار..."):
                    questions = create_quiz(
                        conversation,
                        "اختيار من متعدد",
                        5
                    )

                start_quiz(
                    questions,
                    "اختبار من محادثتنا"
                )

                st.rerun()

            except Exception as e:
                st.error(f"تعذر إنشاء الاختبار: {str(e)}")

        if st.button(
            "بدء محادثة جديدة",
            use_container_width=True
        ):
            st.session_state.chat_history = []
            st.session_state.current_chat_id = None
            st.rerun()


# ==================================================
# 22. RECORDS
# ==================================================

elif st.session_state.page == "records":

    st.title("سجلاتي")
    st.caption("كل ما تحفظينه هنا مرتبط بحسابك.")

    summaries_tab, quizzes_tab, chats_tab = st.tabs([
        "الملخصات",
        "نتائج الاختبارات",
        "المحادثات"
    ])

    with summaries_tab:
        summaries = load_summaries()

        if summaries is None:
            st.error("تعذر تحميل الملخصات.")

            if st.session_state.db_error:
                st.caption(str(st.session_state.db_error)[:500])

        elif not summaries:
            st.info("لا توجد ملخصات محفوظة حتى الآن.")

        else:
            for item in summaries:
                with st.expander(item.get("title") or "ملخص"):
                    st.caption(
                        f"النوع: {item.get('source_type', '—')} · "
                        f"التاريخ: {str(item.get('created_at', ''))[:10]}"
                    )

                    st.markdown(item.get("summary_text", ""))

    with quizzes_tab:
        quiz_records = load_quiz_results()

        if quiz_records is None:
            st.error("تعذر تحميل نتائج الاختبارات.")

            if st.session_state.db_error:
                st.caption(str(st.session_state.db_error)[:500])

        elif not quiz_records:
            st.info("لا توجد نتائج اختبارات محفوظة حتى الآن.")

        else:
            for item in quiz_records:
                title = item.get("title") or "اختبار"
                score = item.get("score", 0)
                total = item.get("total_questions", 0)

                with st.expander(f"{title} — {score}/{total}"):
                    st.caption(
                        f"التاريخ: {str(item.get('created_at', ''))[:10]}"
                    )

                    answers = item.get("answers") or []

                    for i, answer in enumerate(answers, 1):
                        st.markdown(
                            f"**السؤال {i}:** {answer.get('question', '')}"
                        )

                        st.write(
                            f"إجابتك: {answer.get('given', '')}"
                        )

                        st.write(
                            f"الصحيح: {answer.get('correct', '')}"
                        )

                        st.divider()

    with chats_tab:
        chats = load_chat_list()

        if chats is None:
            st.error("تعذر تحميل المحادثات.")

            if st.session_state.db_error:
                st.caption(str(st.session_state.db_error)[:500])

        elif not chats:
            st.info("لا توجد محادثات محفوظة حتى الآن.")

        else:
            for chat in chats:
                title = chat.get("title") or "محادثة"

                if st.button(
                    f"فتح: {title}",
                    key=f"record_chat_{chat.get('id')}",
                    use_container_width=True
                ):
                    if open_chat(chat.get("id")):
                        st.session_state.page = "chat"
                        st.rerun()
                    else:
                        st.error("تعذر فتح المحادثة.")
