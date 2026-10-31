
import streamlit as st
import requests

st.set_page_config(
    page_title="SYNFLOW AI",
    page_icon="🧠",
    layout="wide"
)


# الاتصال بالذكاء الاصطناعي عبر الإنترنت
def ask_ai(prompt):
    try:
        try:
            api_key = st.secrets["GROQ_API_KEY"]
        except Exception:
            api_key = ""

        if not api_key:
            return (
                "لم تتم إضافة مفتاح الذكاء الاصطناعي بعد. "
                "راجعي إعدادات Secrets في Streamlit."
            )

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-oss-20b",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "أنت مساعد دراسي متخصص. "
                            "أجب باللغة العربية، ونظم المعلومات "
                            "بعناوين ونقاط واضحة، وحافظ على "
                            "المعلومات العلمية المهمة."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,
                "max_completion_tokens": 1500
            },
            timeout=120
        )

        if response.status_code == 401:
            return "مفتاح API غير صحيح. راجعي المفتاح في Streamlit Secrets."

        if response.status_code == 429:
            return (
                "وصلنا إلى حد الاستخدام المجاني مؤقتاً. "
                "حاولي مرة أخرى لاحقاً."
            )

        if response.status_code == 404:
            return (
                "تعذر العثور على النموذج المطلوب. "
                "راجعي اسم النموذج في إعدادات التطبيق."
            )

        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        return "استغرق التلخيص وقتاً طويلاً. حاولي مرة أخرى."

    except requests.exceptions.ConnectionError:
        return "تعذر الاتصال بخدمة الذكاء الاصطناعي. تحققي من الإنترنت."

    except Exception as e:
        return f"حدث خطأ أثناء التلخيص: {e}"


# الشريط العلوي
st.html("""
<style>
.synflow-header {
    background: linear-gradient(120deg, #68418A, #8A62AE, #C17FAE);
    width: 100%;
    box-sizing: border-box;
    border-radius: 14px;
    padding: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 18px;
    margin-bottom: 28px;
    direction: ltr;
    box-shadow: 0 12px 30px rgba(112,70,143,0.20);
}

.synflow-logo {
    width: 62px;
    height: 62px;
    border-radius: 50%;
    background: #F3D9ED;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 38px;
}

.synflow-name {
    color: white;
    font-family: Arial, sans-serif;
    font-size: 42px;
    font-weight: 800;
}

@media (max-width: 600px) {
    .synflow-name {
        font-size: 28px;
    }
}
</style>

<div class="synflow-header">
    <div class="synflow-logo">🧠</div>
    <div class="synflow-name">SYNFLOW AI</div>
</div>
""")


# تصميم الموقع
st.html("""
<style>

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 5% 10%,
        rgba(210,180,235,0.22), transparent 28%),
        radial-gradient(circle at 95% 25%,
        rgba(245,205,225,0.25), transparent 25%),
        #FFFFFF;
}

.synflow-name {
    text-shadow: 0 3px 12px rgba(40,15,60,0.18);
}

[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 9px;
    background: #F8F2FC;
    border: 1px solid #EFE3F5;
    padding: 9px;
    border-radius: 16px;
}

[data-testid="stTabs"] button[role="tab"] {
    background: #FFFFFF;
    border: 1px solid #EADCF3;
    border-radius: 12px;
    color: #765394;
    font-size: 15px;
    font-weight: 600;
}

[data-testid="stTabs"] button[aria-selected="true"] {
    background: #EDE1F6;
    border-color: #D7B9E8;
    color: #674487;
}

[data-testid="stFileUploader"] section {
    border: 2px dashed #DABFE8;
    border-radius: 17px;
    background: #FFFBFE;
}

[data-testid="stTextArea"] textarea,
[data-testid="stTextInput"] input {
    border-radius: 13px;
    border-color: #E4D5EF;
}

.stButton button {
    background: linear-gradient(120deg, #8B65B1, #D28CB7);
    color: white;
    border: none;
    border-radius: 13px;
    font-size: 16px;
    font-weight: 700;
    min-height: 45px;
}

.stButton button:hover {
    color: white;
    filter: brightness(1.07);
}

h2, h3 {
    color: #765394;
    font-weight: 700;
}

</style>
""")


# أدوات الدراسة
st.markdown("## أدواتك الدراسية")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 النصوص",
    "📄 PDF",
    "🖼️ الصور",
    "🧠 الاختبارات",
    "🌸 الخرائط الذهنية"
])


# 1- تلخيص النصوص
with tab1:
    st.subheader("تلخيص النصوص")

    lesson = st.text_area("الصقي الدرس هنا:")

    summary_type = st.selectbox(
        "نوع الملخص",
        ["ملخص قصير", "ملخص تفصيلي", "أهم النقاط"]
    )

    if st.button("تلخيص الدرس"):
        if lesson.strip():

            prompt = f"""
            لخص الدرس التالي باللغة العربية.
            نوع الملخص المطلوب: {summary_type}

            نظم الإجابة بعناوين ونقاط واضحة.
            حافظ على المعلومات العلمية المهمة.
            لا تضف معلومات غير موجودة في النص.

            نص الدرس:
            {lesson}
            """

            with st.spinner("جاري تلخيص الدرس..."):
                result = ask_ai(prompt)

            st.markdown("### ✨ الملخص")
            st.write(result)

        else:
            st.warning("الرجاء لصق الدرس أولاً")


# 2- ملفات PDF
with tab2:
    st.subheader("تلخيص ملفات PDF")

    pdf_file = st.file_uploader(
        "ارفعي ملف PDF",
        type=["pdf"]
    )

    st.info(
        "ميزة قراءة وتلخيص ملفات PDF سنضيفها في المرحلة القادمة."
    )


# 3- الصور
with tab3:
    st.subheader("تلخيص الصور")

    image = st.file_uploader(
        "ارفعي صورة الدرس",
        type=["png", "jpg", "jpeg"]
    )

    if image:
        st.image(image, use_container_width=True)

    st.info(
        "ميزة قراءة النصوص من الصور سنضيفها لاحقاً."
    )


# 4- الاختبارات الذكية
with tab4:
    st.subheader("الاختبارات الذكية")

    question_type = st.selectbox(
        "نوع الاختبار",
        ["اختيار من متعدد", "صح أو خطأ", "أسئلة قصيرة"]
    )

    question_count = st.selectbox(
        "عدد الأسئلة",
        [5, 10, 15, 20]
    )

    st.info(
        "سنربط الاختبارات الذكية بالذكاء الاصطناعي في المرحلة القادمة."
    )


# 5- الخرائط الذهنية
with tab5:
    st.subheader("الخرائط الذهنية")

    topic = st.text_input("موضوع الدرس")

    st.info(
        "سنضيف إنشاء الخرائط الذهنية في المرحلة القادمة."
    )
