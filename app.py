import asyncio
from openai import AsyncOpenAI
import streamlit as st
from datetime import datetime

# ========== 페이지 설정 ==========
st.set_page_config(
    page_title="🎙️ Voice Chat AI",
    page_icon="🎙️",
    layout="wide",
)

# ========== Streamlit Secrets에서 설정 읽기 ==========
try:
    REAL_ENDPOINT = st.secrets["real_endpoint"]
    REAL_APIKEY = st.secrets["real_apikey"]
    REAL_DEPLOYMENT = st.secrets["real_deployment"]
except KeyError as e:
    st.error(f"❌ Streamlit secrets 설정 오류: {e}")
    st.stop()

# ========== CSS 스타일링 ==========
st.markdown("""
<style>
    body {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .title-section {
        text-align: center;
        margin-bottom: 30px;
        padding: 20px 0;
    }
    
    .title-section h1 {
        font-size: 48px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# ========== 세션 상태 초기화 ==========
if "messages" not in st.session_state:
    st.session_state.messages = []
if "input_text" not in st.session_state:
    st.session_state.input_text = ""

# ========== UI ==========
st.markdown("""
<div class="title-section">
    <h1>🎙️ AI 음성 어시스턴트</h1>
    <p>텍스트로 입력하면 음성으로 응답합니다</p>
</div>
""", unsafe_allow_html=True)

# ========== 입력 영역 ==========
st.markdown("### 💬 메시지 입력")

col1, col2 = st.columns([4, 1])

with col1:
    user_input = st.text_input(
        "메시지를 입력하세요",
        placeholder="안녕하세요. 오늘 날씨 어때요?",
        label_visibility="collapsed"
    )

with col2:
    send_button = st.button("📤 전송", use_container_width=True)

# ========== AI 응답 처리 ==========
if send_button and user_input:
    # 사용자 메시지 추가
    st.session_state.messages.append({
        "role": "user",
        "content": user_input,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })
    
    # AI 응답 생성
    with st.spinner("🤖 AI가 생각 중..."):
        try:
            base_url = REAL_ENDPOINT.replace("https://", "https://").rstrip("/") + "/openai/api/deployments/" + REAL_DEPLOYMENT + "/chat/completions?api-version=2024-06-01"
            
            # 간단한 REST API 호출
            import requests
            
            headers = {
                "Content-Type": "application/json",
                "api-key": REAL_APIKEY
            }
            
            data = {
                "messages": [
                    {"role": "system", "content": "당신은 친절한 AI 어시스턴트입니다. 한국어로 간결하게 답변하세요."},
                    {"role": "user", "content": user_input}
                ],
                "temperature": 0.7,
                "max_tokens": 1000
            }
            
            response = requests.post(
                f"{REAL_ENDPOINT.rstrip('/')}/openai/deployments/{REAL_DEPLOYMENT}/chat/completions?api-version=2024-06-01",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                ai_response = response.json()["choices"][0]["message"]["content"]
                
                st.session_state.messages.append({
                    "role": "ai",
                    "content": ai_response,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                
                # 입력 초기화
                st.session_state.input_text = ""
                st.rerun()
            else:
                st.error(f"❌ API 오류: {response.status_code}")
                st.error(response.text)
                
        except Exception as e:
            st.error(f"❌ 오류: {str(e)}")

# ========== 대화 표시 ==========
st.markdown("### 💬 대화 기록")

chat_container = st.container(border=True)

with chat_container:
    if st.session_state.messages:
        for message in st.session_state.messages:
            if message["role"] == "user":
                st.markdown(f"""
                <div style="text-align: right; margin-bottom: 15px;">
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                color: white; padding: 12px 16px; border-radius: 15px 15px 0px 15px;
                                display: inline-block; max-width: 80%; word-wrap: break-word;">
                        <b>👤 You</b><br/>
                        {message['content']}
                        <br/>
                        <span style="font-size: 0.75rem; opacity: 0.8;">{message['timestamp']}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="text-align: left; margin-bottom: 15px;">
                    <div style="background: #e9ecef; color: #333; padding: 12px 16px; 
                                border-radius: 15px 15px 15px 0px; display: inline-block; 
                                max-width: 80%; word-wrap: break-word;">
                        <b>🤖 AI</b><br/>
                        {message['content']}
                        <br/>
                        <span style="font-size: 0.75rem; opacity: 0.7;">{message['timestamp']}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("💡 메시지를 입력하고 전송 버튼을 클릭하세요")

# ========== 통계 ==========
st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("📊 총 메시지", len(st.session_state.messages))

with col2:
    user_msgs = len([m for m in st.session_state.messages if m["role"] == "user"])
    st.metric("👤 사용자 메시지", user_msgs)

with col3:
    ai_msgs = len([m for m in st.session_state.messages if m["role"] == "ai"])
    st.metric("🤖 AI 메시지", ai_msgs)

# ========== 하단 ==========
st.markdown("""
---
<div style="text-align: center; color: #999; font-size: 0.85rem; padding: 20px;">
    <p>🔒 모든 대화는 Azure OpenAI API를 통해 처리됩니다</p>
    <p style="margin-top: 10px; font-size: 0.75rem;">설정: .streamlit/secrets.toml</p>
</div>
""", unsafe_allow_html=True)
