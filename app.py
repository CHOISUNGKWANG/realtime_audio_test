import streamlit as st
from openai import AzureOpenAI
from datetime import datetime
import io

# ========== 페이지 설정 ==========
st.set_page_config(
    page_title="🎙️ Voice Chat AI",
    page_icon="🎙️",
    layout="wide",
)

# ========== Secrets 읽기 ==========
try:
    ENDPOINT = st.secrets["real_endpoint"]
    API_KEY = st.secrets["real_apikey"]
    DEPLOYMENT = st.secrets["real_deployment"]
except KeyError as e:
    st.error(f"❌ Secrets 설정 오류: {e}")
    st.stop()

# ========== CSS ==========
st.markdown("""
<style>
    body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .title { text-align: center; margin-bottom: 30px; }
    .title h1 {
        font-size: 48px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
</style>
""", unsafe_allow_html=True)

# ========== 세션 상태 ==========
if "messages" not in st.session_state:
    st.session_state.messages = []

# ========== UI ==========
st.markdown('<div class="title"><h1>🎙️ Voice Chat AI</h1><p>음성으로 AI와 대화</p></div>', unsafe_allow_html=True)

# ========== Azure 클라이언트 초기화 ==========
client = AzureOpenAI(
    api_key=API_KEY,
    api_version="2024-08-01-preview",
    azure_endpoint=ENDPOINT
)

# ========== 입력 섹션 ==========
st.markdown("### 🎤 음성 입력")

col1, col2 = st.columns([3, 1])

with col1:
    audio_file = st.file_uploader(
        "음성 파일 선택 (WAV, MP3, M4A)",
        type=["wav", "mp3", "m4a"],
        label_visibility="collapsed"
    )

with col2:
    send_button = st.button("📤 전송", use_container_width=True)

# ========== 처리 로직 ==========
if send_button and audio_file:
    with st.spinner("⏳ 처리 중..."):
        try:
            # 파일 데이터 읽기
            audio_bytes = audio_file.read()
            
            # Step 1: STT (음성 → 텍스트)
            st.write("📝 음성을 텍스트로 변환...")
            
            # 파일 객체 생성
            audio_file_obj = io.BytesIO(audio_bytes)
            audio_file_obj.name = "audio.wav"
            
            # Whisper API 호출
            transcript_result = client.audio.transcriptions.create(
                model="whisper",
                file=audio_file_obj,
                language="ko"
            )
            
            user_text = transcript_result.text
            st.success(f"✅ 인식됨: '{user_text}'")
            
            # 사용자 메시지 저장
            st.session_state.messages.append({
                "role": "user",
                "content": user_text,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
            
            # Step 2: LLM (텍스트 응답)
            st.write("🤖 AI가 응답 중...")
            
            response = client.chat.completions.create(
                model=DEPLOYMENT,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 친절한 AI 어시스턴트입니다. 한국어로 자연스럽고 간결하게 답변하세요."
                    },
                    {
                        "role": "user",
                        "content": user_text
                    }
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            ai_text = response.choices[0].message.content
            st.success(f"✅ 응답 생성 완료")
            
            # AI 메시지 저장
            st.session_state.messages.append({
                "role": "ai",
                "content": ai_text,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
            
            # Step 3: TTS (텍스트 → 음성)
            st.write("🔊 음성 합성 중...")
            
            speech = client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=ai_text
            )
            
            st.success("✅ 음성 생성 완료")
            
            # 음성 재생
            st.audio(speech.content, format="audio/wav")
            
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 오류: {str(e)}")

# ========== 대화 기록 ==========
st.markdown("---")
st.markdown("### 💬 대화 기록")

if st.session_state.messages:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f"""
            <div style="text-align: right; margin-bottom: 10px;">
                <div style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 12px 16px;
                    border-radius: 15px 15px 0px 15px;
                    display: inline-block;
                    max-width: 80%;
                    word-wrap: break-word;
                ">
                    <b>👤 You</b><br/>
                    {msg['content']}<br/>
                    <span style="font-size: 0.75rem; opacity: 0.8;">{msg['timestamp']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="text-align: left; margin-bottom: 10px;">
                <div style="
                    background: #e9ecef;
                    color: #333;
                    padding: 12px 16px;
                    border-radius: 15px 15px 15px 0px;
                    display: inline-block;
                    max-width: 80%;
                    word-wrap: break-word;
                ">
                    <b>🤖 AI</b><br/>
                    {msg['content']}<br/>
                    <span style="font-size: 0.75rem; opacity: 0.7;">{msg['timestamp']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("💡 음성 파일을 업로드하고 전송하면 대화가 시작됩니다")

# ========== 통계 ==========
st.markdown("---")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("📊 총 메시지", len(st.session_state.messages))

with col2:
    user_count = len([m for m in st.session_state.messages if m["role"] == "user"])
    st.metric("👤 사용자", user_count)

with col3:
    ai_count = len([m for m in st.session_state.messages if m["role"] == "ai"])
    st.metric("🤖 AI", ai_count)

# ========== 설명 ==========
with st.expander("📖 사용 방법"):
    st.markdown("""
    ### 🎙️ 음성 대화 방법
    
    **Step 1: 음성 파일 준비**
    - 마이크로 음성 녹음 또는
    - 기존 음성 파일 사용
    
    **Step 2: 파일 업로드**
    - WAV, MP3, M4A 형식 지원
    - 파일 선택 후 "📤 전송" 클릭
    
    **Step 3: 자동 처리**
    - STT: 음성 → 텍스트 (Azure Whisper)
    - LLM: AI 응답 생성 (Azure OpenAI)
    - TTS: 텍스트 → 음성 (Azure Speech)
    
    **Step 4: 결과 확인**
    - 텍스트 응답 표시
    - 음성 자동 재생
    """)

# ========== 정보 ==========
st.markdown("""
---
<div style="text-align: center; color: #999; font-size: 0.85rem; padding: 20px;">
    <p>🔒 모든 대화는 Azure OpenAI API를 통해 처리됩니다</p>
    <p style="margin-top: 10px; font-size: 0.75rem;">Whisper (STT) → GPT (LLM) → Azure TTS</p>
</div>
""", unsafe_allow_html=True)
