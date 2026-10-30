import streamlit as st
import requests
st.set_page_config(
    page_title="SYNFLOW AI",
    page_icon="🧠",
    layout="wide"
)

def ask_ai(prompt):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.2",
            "prompt": prompt,
            "stream": False
        }
    )
    return response.json()["response"]

# الشريط العلوي
st.html("""
<style>
.synflow-header {
    background-color: #70468F;
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
    letter-spacing: 1px;
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

st.html("""
<style>

/* خلفية ناعمة */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 5% 10%,
        rgba(210,180,235,0.22), transparent 28%),
        radial-gradient(circle at 95% 25%,
        rgba(245,205,225,0.25), transparent 25%),
        #FFFFFF;
}

/* الشريط العلوي */
.synflow-header {
    background: linear-gradient(
        120deg, #68418A, #8A62AE, #C17FAE
    ) !important;
    box-shadow: 0 12px 30px rgba(112,70,143,0.20);
}

/* شعار الدماغ */
.synflow-logo {
    box-shadow:
        0 0 0 6px rgba(255,255,255,0.18),
        0 5px 15px rgba(60,25,80,0.15);
}

/* اسم الموقع */
.synflow-name {
    text-shadow: 0 3px 12px rgba(40,15,60,0.18);
}

/* شريط الأدوات */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 9px;
    background: #F8F2FC;
    border: 1px solid #EFE3F5;
    padding: 9px;
    border-radius: 16px;
}

/* أزرار التبويبات */
[data-testid="stTabs"] button[role="tab"] {
    background: #FFFFFF;
    border: 1px solid #EADCF3;
    border-radius: 12px;
    color: #765394;
    font-size: 15px;
    font-weight: 600;
}

/* التبويب المحدد */
[data-testid="stTabs"] button[aria-selected="true"] {
    background: #EDE1F6;
    border-color: #D7B9E8;
    color: #674487;
}

/* مربعات رفع الملفات */
[data-testid="stFileUploader"] section {
    border: 2px dashed #DABFE8;
    border-radius: 17px;
    background: #FFFBFE;
}

/* حقول الكتابة */
[data-testid="stTextArea"] textarea,
[data-testid="stTextInput"] input {
    border-radius: 13px;
    border-color: #E4D5EF;
}

/* الأزرار */
.stButton button {
    background: linear-gradient(
        120deg, #8B65B1, #D28CB7
    );
    color: white;
    border: none;
    border-radius: 13px;
    font-size: 16px;
    font-weight: 700;
    min-height: 45px;
    box-shadow: 0 5px 14px rgba(145,102,178,0.15);
}

.stButton button:hover {
    color: white;
    filter: brightness(1.07);
}

/* العناوين */
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

with tab1:
    st.subheader("تلخيص النصوص")
    lesson = st.text_area("الصقي الدرس هنا:")
    st.selectbox(
        "نوع الملخص",
        ["ملخص قصير", "ملخص تفصيلي", "أهم النقاط"]
    )
   
    if st.button("تلخيص الدرس"):
        if lesson.strip():
            with st.spinner("جاري تلخيص الدرس..."):
                result = ask_ai(
                    "لخص الدرس التالي باللغة العربية، "
                    "ونظم الأفكار في نقاط واضحة:\n\n" + lesson
                )
            st.markdown("### ✨ الملخص")
            st.write(result)
        else:
            st.warning("الرجاء لصق الدرس أولاً")

with tab2:
    st.subheader("تلخيص ملفات PDF")
    st.file_uploader("ارفعي ملف PDF", type=["pdf"])

with tab3:
    st.subheader("تلخيص الصور")
    image = st.file_uploader(
        "ارفعي صورة الدرس",
        type=["png", "jpg", "jpeg"]
    )
    if image:
        st.image(image, use_container_width=True)

with tab4:
    st.subheader("الاختبارات الذكية")
    st.selectbox(
        "نوع الاختبار",
        ["اختيار من متعدد", "صح أو خطأ", "أسئلة قصيرة"]
    )
    st.selectbox("عدد الأسئلة", [5, 10, 15, 20])

with tab5:
    st.subheader("الخرائط الذهنية")
    st.text_input("موضوع الدرس")

    st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background-color: #FFFFFF !important;

    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='220' viewBox='0 0 260 220'%3E%3Cg fill='none' stroke='%23E8B9D3' stroke-width='2' opacity='0.32'%3E%3Cellipse cx='130' cy='110' rx='48' ry='17'/%3E%3Cellipse cx='130' cy='110' rx='48' ry='17' transform='rotate(60 130 110)'/%3E%3Cellipse cx='130' cy='110' rx='48' ry='17' transform='rotate(120 130 110)'/%3E%3C/g%3E%3Ccircle cx='130' cy='110' r='3' fill='%23E8B9D3' opacity='0.32'/%3E%3Ccircle cx='178' cy='110' r='3' fill='%23E8B9D3' opacity='0.32'/%3E%3C/svg%3E");

    background-repeat: repeat !important;
    background-size: 280px 240px !important;
}
</style>
""", unsafe_allow_html=True)

