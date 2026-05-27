import os
import base64
import asyncio
import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI
import streamlit as st
from datetime import datetime
import queue

# ========== 페이지 설정 ==========
st.set_page_config(
    page_title="🎙️ Voice Chat AI",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ========== Streamlit Secrets에서 설정 읽기 ==========
try:
    REAL_ENDPOINT = st.secrets["real_endpoint"]
    REAL_APIKEY = st.secrets["real_apikey"]
    REAL_DEPLOYMENT = st.secrets["real_deployment"]
except KeyError as e:
    st.error(f"❌ Streamlit secrets 설정 오류: {e}")
    st.error("💡 .streamlit/secrets.toml 파일에 다음을 추가하세요:")
    st.code("""
real_endpoint = 'https://your-resource.openai.azure.com/'
real_apikey = 'your_api_key'
real_deployment = 'gpt-4-realtime-preview'
    """)
    st.stop()

# ========== CSS 스타일링 ==========
st.markdown("""
<style>
    * {
        margin: 0;
        padding: 0;
    }
    
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
    }
    
    .main {
        background: white;
        border-radius: 20px;
        padding: 0;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
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
    
    .title-section p {
        color: #666;
        font-size: 16px;
    }
    
    .settings-box {
        background: #f0f4ff;
        border-left: 4px solid #667eea;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ========== 세션 상태 초기화 ==========
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_recording" not in st.session_state:
    st.session_state.is_recording = False
if "status" not in st.session_state:
    st.session_state.status = "대기 중..."

# ========== 오디오 설정 ==========
SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 2400

# ========== 전역 변수 ==========
mic_queue = queue.Queue()
speaker_buffer = bytearray()
is_ai_speaking = False
current_ai_transcript = ""

def mic_callback(indata, frames, time_info, status):
    """마이크 입력 콜백"""
    if status:
        pass
    
    global is_ai_speaking
    if is_ai_speaking:
        return
        
    pcm_bytes = indata.tobytes()
    try:
        mic_queue.put_nowait(pcm_bytes)
    except queue.Full:
        pass

def speaker_callback(outdata, frames, time_info, status):
    """스피커 출력 콜백"""
    global is_ai_speaking, speaker_buffer
    
    required_bytes = frames * CHANNELS * 2
    if len(speaker_buffer) >= required_bytes:
        data = speaker_buffer[:required_bytes]
        del speaker_buffer[:required_bytes]
        
        outdata[:] = np.frombuffer(data, dtype=np.int16).reshape(-1, CHANNELS)
        is_ai_speaking = True
    else:
        outdata.fill(0)
        is_ai_speaking = False

async def send_mic_audio(connection):
    """마이크 입력 전송"""
    global is_ai_speaking
    while st.session_state.is_recording:
        try:
            pcm_bytes = mic_queue.get(timeout=0.1)
            
            if is_ai_speaking:
                continue
                
            b64_audio = base64.b64encode(pcm_bytes).decode()
            await connection.input_audio_buffer.append(audio=b64_audio)
        except queue.Empty:
            await asyncio.sleep(0.01)
        except Exception as e:
            st.error(f"❌ 마이크 입력 에러: {e}")
            break

async def receive_server_audio(connection):
    """서버 응답 수신"""
    global speaker_buffer, current_ai_transcript
    
    async for event in connection:
        if event.type == "response.output_audio.delta":
            audio_chunk = base64.b64decode(event.delta)
            speaker_buffer.extend(audio_chunk)
                
        elif event.type == "conversation.item.input_audio_transcription.completed":
            user_text = event.transcript.strip()
            if user_text:
                st.session_state.messages.append({
                    "role": "user",
                    "content": user_text,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                st.session_state.status = "🤖 AI가 생각 중..."
                st.rerun()
            
        elif event.type == "response.output_audio_transcript.delta":
            current_ai_transcript += event.delta

        elif event.type == "response.done":
            ai_text = current_ai_transcript.strip()
            if ai_text:
                st.session_state.messages.append({
                    "role": "ai",
                    "content": ai_text,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
            current_ai_transcript = ""
            st.session_state.status = "🎤 청취 중..."
            st.rerun()
            
        elif event.type == "error":
            st.error(f"❌ 서버 에러: {event.error.message}")
            st.session_state.is_recording = False
            break

async def run_voice_chat():
    """음성채팅 실행"""
    base_url = REAL_ENDPOINT.replace("https://", "wss://").rstrip("/") + "/openai/v1"
    
    try:
        # 사용 가능한 장치 확인
        try:
            devices = sd.query_devices()
        except Exception as e:
            st.error(f"❌ 오디오 장치 조회 실패: {e}")
            st.session_state.is_recording = False
            return
        
        # 입력/출력 장치 찾기
        input_devices = [i for i, d in enumerate(devices) if d['max_input_channels'] > 0]
        output_devices = [i for i, d in enumerate(devices) if d['max_output_channels'] > 0]
        
        if not input_devices:
            st.error("❌ 입력 장치(마이크)를 찾을 수 없습니다!")
            st.info("💡 시스템 설정에서 마이크를 확인하세요")
            st.session_state.is_recording = False
            return
        
        if not output_devices:
            st.error("❌ 출력 장치(스피커)를 찾을 수 없습니다!")
            st.session_state.is_recording = False
            return
        
        # 기본 장치 사용
        default_input = input_devices[0]
        default_output = output_devices[0]
        
        st.info(f"🎤 사용 중인 입력: {devices[default_input]['name']}")
        st.info(f"🔊 사용 중인 출력: {devices[default_output]['name']}")
        
        client = AsyncOpenAI(websocket_base_url=base_url, api_key=REAL_APIKEY)

        # 스트림 생성
        try:
            mic_stream = sd.InputStream(
                device=default_input,
                samplerate=SAMPLE_RATE, 
                channels=CHANNELS, 
                dtype='int16', 
                blocksize=CHUNK_SIZE,
                callback=mic_callback,
                latency='low'
            )
            
            speaker_stream = sd.OutputStream(
                device=default_output,
                samplerate=SAMPLE_RATE, 
                channels=CHANNELS, 
                dtype='int16',
                blocksize=CHUNK_SIZE,
                callback=speaker_callback,
                latency='low'
            )
        except Exception as e:
            st.error(f"❌ 스트림 생성 실패: {e}")
            st.session_state.is_recording = False
            return

        with mic_stream, speaker_stream:
            async with client.realtime.connect(model=REAL_DEPLOYMENT) as connection:
                await connection.session.update(
                    session={
                        "type": "realtime",
                        "instructions": "당신은 친절하고 자연스럽게 대화하는 AI 도우미입니다. 모든 답변은 한국어로 간결하고 대화하듯이 친숙하게 하세요.",
                        "output_modalities": ["audio"],
                        "audio": {
                            "input": {
                                "transcription": {"model": "whisper-1"},
                                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.7,
                                    "prefix_padding_ms": 300,
                                    "silence_duration_ms": 1000, 
                                    "create_response": True,
                                    "interrupt_response": True 
                                },
                            },
                            "output": {
                                "voice": "alloy",
                                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                            },
                        },
                    }
                )

                st.session_state.status = "🎤 청취 중..."
                st.rerun()

                await asyncio.gather(
                    send_mic_audio(connection),
                    receive_server_audio(connection)
                )
    except Exception as e:
        st.error(f"❌ 연결 에러: {e}")
        st.session_state.is_recording = False

# ========== UI ==========
st.markdown("""
<div class="title-section">
    <h1>🎙️ Voice Chat AI</h1>
    <p>실시간 음성으로 AI와 대화하세요</p>
</div>
""", unsafe_allow_html=True)

# ========== 설정 정보 ==========
st.markdown(f"""
<div class="settings-box">
    <p>✅ <b>Azure 설정 로드됨</b></p>
    <ul style="margin-left: 20px;">
        <li>🔗 Endpoint: {REAL_ENDPOINT.split('.')[0]}...</li>
        <li>🤖 Deployment: {REAL_DEPLOYMENT}</li>
        <li>🔑 API Key: {REAL_APIKEY[:10]}...{REAL_APIKEY[-5:]}</li>
    </ul>
</div>
""", unsafe_allow_html=True)

# ========== 상태 표시 ==========
col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    status_emoji = "🟢" if st.session_state.is_recording else "⚪"
    st.markdown(f"**상태:** {status_emoji} {st.session_state.status}")

with col3:
    if st.session_state.is_recording:
        if st.button("⏹️ 종료", use_container_width=True, key="stop_btn"):
            st.session_state.is_recording = False
            st.session_state.status = "대기 중..."
            st.rerun()
    else:
        if st.button("🎤 시작", use_container_width=True, key="start_btn"):
            st.session_state.is_recording = True
            st.session_state.status = "🎤 청취 중..."
            
            try:
                asyncio.run(run_voice_chat())
            except KeyboardInterrupt:
                st.session_state.is_recording = False
            except Exception as e:
                st.error(f"❌ 에러: {e}")
                st.session_state.is_recording = False

# ========== 채팅 영역 ==========
st.markdown("### 💬 대화 기록")

chat_container = st.container(border=True)

with chat_container:
    if st.session_state.messages:
        for message in st.session_state.messages:
            if message["role"] == "user":
                st.markdown(f"""
                <div style="text-align: right; margin-bottom: 10px;">
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
                <div style="text-align: left; margin-bottom: 10px;">
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
        st.markdown("""
        <div style="text-align: center; color: #999; padding: 40px;">
            <h3>아직 메시지가 없습니다</h3>
            <p>🎤 시작 버튼을 눌러 음성 채팅을 시작하세요</p>
        </div>
        """, unsafe_allow_html=True)

# ========== 정보 섹션 ==========
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

# ========== 하단 정보 ==========
st.markdown("""
---
<div style="text-align: center; color: #999; font-size: 0.85rem; padding: 20px;">
    <p>💡 마이크에 명확하게 말씀하고, 말을 마친 후 1초 침묵하면 AI가 응답합니다</p>
    <p>🔒 모든 대화는 Azure OpenAI Realtime API를 통해 처리됩니다</p>
    <p style="margin-top: 10px; font-size: 0.75rem;">설정: .streamlit/secrets.toml</p>
</div>
""", unsafe_allow_html=True)
