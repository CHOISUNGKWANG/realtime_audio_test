import streamlit as st
import base64
import numpy as np
from openai import AzureOpenAI
from datetime import datetime
import io

# ========== 페이지 설정 ==========
st.set_page_config(
    page_title="🎙️ Real-time Voice Chat",
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

# ========== CSS 스타일링 ==========
st.markdown("""
<style>
    body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .title-section { text-align: center; margin-bottom: 30px; padding: 20px 0; }
    .title-section h1 {
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
if "recording" not in st.session_state:
    st.session_state.recording = False

# ========== UI ==========
st.markdown("""
<div class="title-section">
    <h1>🎙️ Real-time Voice Chat AI</h1>
    <p>브라우저 마이크로 실시간 음성 대화</p>
</div>
""", unsafe_allow_html=True)

# ========== 웹 오디오 레코더 컴포넌트 ==========
st.markdown("""
### 🎤 음성 녹음

<div id="recordingContainer" style="background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center;">
    <button id="recordBtn" onclick="startRecording()" style="
        padding: 12px 24px; font-size: 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; border: none; border-radius: 8px; cursor: pointer; margin-right: 10px;
    ">🎤 녹음 시작</button>
    
    <button id="stopBtn" onclick="stopRecording()" style="
        padding: 12px 24px; font-size: 16px; background: #ff6b6b;
        color: white; border: none; border-radius: 8px; cursor: pointer; display: none;
    ">⏹️ 중지</button>
    
    <span id="timer" style="margin-left: 20px; font-size: 14px; color: #666;"></span>
    <div id="waveform" style="height: 50px; margin-top: 10px; display: none;">
        <canvas id="waveformCanvas" style="width: 100%; height: 100%;"></canvas>
    </div>
</div>

<script>
let mediaRecorder;
let audioChunks = [];
let recordingStartTime;
let timerInterval;
let audioContext;
let analyser;
let animationId;

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        const source = audioContext.createMediaStreamSource(stream);
        source.connect(analyser);
        
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        recordingStartTime = Date.now();
        
        mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
        mediaRecorder.onstop = () => {
            stream.getTracks().forEach(t => t.stop());
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            const url = URL.createObjectURL(audioBlob);
            document.getElementById('audioOutput').src = url;
            
            // Base64로 변환해서 Streamlit에 전송
            const reader = new FileReader();
            reader.onload = () => {
                window.parent.postMessage({
                    type: 'audioData',
                    data: reader.result.split(',')[1]
                }, '*');
            };
            reader.readAsDataURL(audioBlob);
        };
        
        mediaRecorder.start();
        document.getElementById('recordBtn').style.display = 'none';
        document.getElementById('stopBtn').style.display = 'inline-block';
        document.getElementById('waveform').style.display = 'block';
        
        // 타이머
        timerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
            const min = Math.floor(elapsed / 60);
            const sec = elapsed % 60;
            document.getElementById('timer').textContent = 
                `${min}:${sec.toString().padStart(2, '0')}`;
        }, 100);
        
        // 파형 그리기
        drawWaveform();
    } catch (error) {
        alert('마이크 접근 거부: ' + error.message);
    }
}

function drawWaveform() {
    const canvas = document.getElementById('waveformCanvas');
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    
    const draw = () => {
        animationId = requestAnimationFrame(draw);
        analyser.getByteFrequencyData(dataArray);
        
        ctx.fillStyle = '#f8f9fa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#667eea';
        
        const barWidth = (canvas.width / dataArray.length) * 2.5;
        let x = 0;
        
        for (let i = 0; i < dataArray.length; i++) {
            const barHeight = (dataArray[i] / 255) * canvas.height;
            ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
            x += barWidth + 1;
        }
    };
    draw();
}

function stopRecording() {
    mediaRecorder.stop();
    document.getElementById('recordBtn').style.display = 'inline-block';
    document.getElementById('stopBtn').style.display = 'none';
    document.getElementById('timer').textContent = '';
    document.getElementById('waveform').style.display = 'none';
    clearInterval(timerInterval);
    cancelAnimationFrame(animationId);
}
</script>

<audio id="audioOutput" controls style="width: 100%; margin-top: 10px; display: none;"></audio>
""", unsafe_allow_html=True)

# ========== 파일 업로드 또는 녹음 처리 ==========
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 📤 또는 파일 업로드")
    uploaded_file = st.file_uploader("음성 파일 선택", type=["wav", "mp3", "m4a"])

with col2:
    st.markdown("")
    process_btn = st.button("🎯 전송 및 처리", use_container_width=True, key="process")

# ========== AI 처리 ==========
if process_btn:
    if uploaded_file:
        # 파일 처리
        audio_data = uploaded_file.read()
        
        with st.spinner("🤖 AI가 처리 중..."):
            try:
                client = AzureOpenAI(
                    api_key=API_KEY,
                    api_version="2024-06-01",
                    azure_endpoint=ENDPOINT
                )
                
                # STT (음성 → 텍스트)
                with io.BytesIO(audio_data) as audio_file:
                    audio_file.name = "audio.wav"
                    transcript = client.audio.transcriptions.create(
                        model="whisper",
                        file=audio_file,
                        language="ko"
                    )
                
                user_text = transcript.text
                
                # 사용자 메시지 추가
                st.session_state.messages.append({
                    "role": "user",
                    "content": user_text,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                
                # LLM 응답
                response = client.chat.completions.create(
                    model=DEPLOYMENT,
                    messages=[
                        {"role": "system", "content": "당신은 친절한 AI 어시스턴트입니다. 한국어로 간결하게 답변하세요."},
                        {"role": "user", "content": user_text}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                
                ai_text = response.choices[0].message.content
                
                # AI 메시지 추가
                st.session_state.messages.append({
                    "role": "ai",
                    "content": ai_text,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                
                # TTS (텍스트 → 음성)
                speech = client.audio.speech.create(
                    model="tts-1",
                    voice="alloy",
                    input=ai_text
                )
                
                # 음성 재생
                st.audio(speech.content, format="audio/wav")
                
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 오류: {str(e)}")
    else:
        st.warning("⚠️ 음성 파일을 업로드하거나 녹음을 완료하세요")

# ========== 대화 기록 ==========
st.markdown("---")
st.markdown("### 💬 대화 기록")

chat_container = st.container(border=True)

with chat_container:
    if st.session_state.messages:
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(f"""
                <div style="text-align: right; margin-bottom: 15px;">
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                color: white; padding: 12px 16px; border-radius: 15px 15px 0px 15px;
                                display: inline-block; max-width: 80%; word-wrap: break-word;">
                        <b>👤 You</b><br/>
                        {msg['content']}
                        <span style="font-size: 0.75rem; opacity: 0.8; margin-top: 5px; display: block;">{msg['timestamp']}</span>
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
                        {msg['content']}
                        <span style="font-size: 0.75rem; opacity: 0.7; margin-top: 5px; display: block;">{msg['timestamp']}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("💡 음성을 녹음하거나 파일을 업로드한 후 '전송 및 처리'를 클릭하세요")

# ========== 통계 ==========
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("📊 총 메시지", len(st.session_state.messages))
with col2:
    user_count = len([m for m in st.session_state.messages if m["role"] == "user"])
    st.metric("👤 사용자 메시지", user_count)
with col3:
    ai_count = len([m for m in st.session_state.messages if m["role"] == "ai"])
    st.metric("🤖 AI 메시지", ai_count)

# ========== 설명 ==========
with st.expander("📖 사용 방법"):
    st.markdown("""
    ### 🎙️ 실시간 음성 대화
    
    #### **방법 1: 브라우저 녹음**
    1. 🎤 녹음 시작 클릭
    2. 마이크 권한 허용
    3. 명확하게 말하기
    4. ⏹️ 중지 클릭
    5. 🎯 전송 및 처리
    
    #### **방법 2: 파일 업로드**
    1. 📤 파일 선택
    2. WAV, MP3, M4A 지원
    3. 🎯 전송 및 처리
    
    #### **결과**
    - 음성 → 텍스트 변환 (STT)
    - AI가 텍스트로 응답
    - 텍스트 → 음성 변환 (TTS)
    - 자동 음성 재생
    """)
