import os
import base64
import asyncio
import numpy as np
import sounddevice as sd
import streamlit as st
from openai import AsyncOpenAI

# 1. 페이지 설정 및 UI 구성
st.set_page_config(page_title="Azure Realtime Voice Chat", page_icon="🎙️", layout="centered")
st.title("🎙️ Azure Realtime 음성 비서")
st.caption("마이크로 대화하고 스피커로 답변을 듣는 실시간 음성 서비스입니다.")

# 오디오 설정 상수
SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 2400  # 100ms 단위

# 2. 비동기 루프 및 큐를 세션 상태(Session State)에 안전하게 초기화
if "loop" not in st.session_state:
    st.session_state.loop = asyncio.new_event_loop()
if "mic_queue" not in st.session_state:
    st.session_state.mic_queue = asyncio.Queue()
if "speaker_buffer" not in st.session_state:
    st.session_state.speaker_buffer = bytearray()
if "is_ai_speaking" not in st.session_state:
    st.session_state.is_ai_speaking = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # 화면 표시용 대화록
if "connected" not in st.session_state:
    st.session_state.connected = False

# 오디오 장치 콜백 함수들
def mic_callback(indata, frames, time_info, status):
    if status:
        st.warning(f"🎤 마이크 입력 경고: {status}")
    if st.session_state.is_ai_speaking:
        return
    pcm_bytes = indata.tobytes()
    st.session_state.loop.call_soon_threadsafe(st.session_state.mic_queue.put_nowait, pcm_bytes)

def speaker_callback(outdata, frames, time_info, status):
    required_bytes = frames * CHANNELS * 2
    buffer = st.session_state.speaker_buffer
    if len(buffer) >= required_bytes:
        data = buffer[:required_bytes]
        del buffer[:required_bytes]
        outdata[:] = np.frombuffer(data, dtype=np.int16).reshape(-1, CHANNELS)
        st.session_state.is_ai_speaking = True
    else:
        outdata.fill(0)
        st.session_state.is_ai_speaking = False

# 비동기 백그라운드 태스크들
async def send_mic_audio(connection):
    while st.session_state.connected:
        pcm_bytes = await st.session_state.mic_queue.get()
        if st.session_state.is_ai_speaking:
            st.session_state.mic_queue.task_done()
            continue
        b64_audio = base64.b64encode(pcm_bytes).decode()
        await connection.input_audio_buffer.append(audio=b64_audio)
        st.session_state.mic_queue.task_done()
        await asyncio.sleep(0.01)

async def receive_server_audio(connection):
    current_ai_transcript = ""
    while st.session_state.connected:
        async for event in connection:
            if event.type == "response.output_audio.delta":
                audio_chunk = base64.b64decode(event.delta)
                st.session_state.speaker_buffer.extend(audio_chunk)
                    
            elif event.type == "conversation.item.input_audio_transcription.completed":
                user_text = event.transcript.strip()
                if user_text:
                    st.session_state.chat_history.append({"role": "user", "content": user_text})
                    st.rerun() # 자막 갱신을 위해 스트림릿 강제 리렌더링
                
            elif event.type == "response.output_audio_transcript.delta":
                current_ai_transcript += event.delta

            elif event.type == "response.done":
                ai_text = current_ai_transcript.strip()
                if ai_text:
                    st.session_state.chat_history.append({"role": "assistant", "content": ai_text})
                    st.rerun() # 자막 갱신을 위해 스트림릿 강제 리렌더링
                current_ai_transcript = ""
                
            elif event.type == "error":
                st.error(f"서버 에러: {event.error.message}")

# 대화 시작 통합 비동기 함수
async def start_realtime_session():
    # 환경 변수 로드 (사용자 환경 변수 명칭 유지)
    endpoint = real_endpoint
    deployment_name = real_deployment
    token = real_apikey
    base_url = endpoint.replace("https://", "wss://").rstrip("/") + "/openai/v1"

    client = AsyncOpenAI(websocket_base_url=base_url, api_key=token)

    mic_stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16', 
        blocksize=CHUNK_SIZE, callback=lambda indata, frames, time, status: mic_callback(indata, frames, time, status)
    )
    speaker_stream = sd.OutputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16', 
        blocksize=CHUNK_SIZE, callback=speaker_callback
    )

    with mic_stream, speaker_stream:
        async with client.realtime.connect(model=deployment_name) as connection:
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
                                "threshold": 0.6,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 600, 
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
            st.session_state.connected = True
            st.rerun() # 상태 변경 반영

            await asyncio.gather(
                send_mic_audio(connection),
                receive_server_audio(connection)
            )

# 3. 사이드바 제어 버튼 UI
st.sidebar.header("🕹️ 대화 컨트롤러")
if not st.session_state.connected:
    if st.sidebar.button("🟢 음성 대화 시작", use_container_width=True):
        st.sidebar.info("🎙️ 마이크가 켜졌습니다. 말씀하세요.")
        # 비동기 함수 루프 실행
        st.session_state.loop.run_until_complete(start_realtime_session())
else:
    if st.sidebar.button("🔴 음성 대화 종료", use_container_width=True):
        st.session_state.connected = False
        st.session_state.speaker_buffer.clear()
        st.sidebar.warning("⏹️ 대화가 종료되었습니다.")
        st.rerun()

if st.sidebar.button("🧹 대화창 비우기", use_container_width=True):
    st.session_state.chat_history = []
    st.rerun()

# 4. 메인 화면 대화창 출력 (말풍선 UI)
st.write("---")
for chat in st.session_state.chat_history:
    with st.chat_message(chat["role"]):
        st.write(chat["content"])

# 연결 상태에 따른 하단 안내 메시지
if st.session_state.connected:
    st.info("💡 실시간 연결 중입니다. 대화가 끝나면 한 문장씩 대화창에 업데이트됩니다.")
