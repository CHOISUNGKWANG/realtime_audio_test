import os
import base64
import asyncio
import streamlit as st
from openai import AsyncOpenAI
# 💡 웹 브라우저 마이크 녹음기 임포트
from streamlit_mic_recorder import mic_recorder

st.set_page_config(page_title="Azure Realtime Voice Chat", page_icon="🎙️", layout="centered")
st.title("🎙️ Azure Realtime 웹 음성 비서")
st.caption("웹 브라우저의 마이크를 이용해 실시간으로 대화하는 챗봇입니다.")

# 세션 상태 초기화
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# 가상의 이벤트 루프 생성 함수 (스트림릿 클라우드 비동기 대응용)
def get_or_create_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

# 💡 핵심: 녹음된 바이너리 데이터를 Azure Realtime API에 한 번에 던져서 오디오 답변을 받는 함수
async def process_voice_chat(audio_bytes):
    # Streamlit Secrets에서 보안 변수 로드
    endpoint = st.secrets["REAL_ENDPOINT"]
    deployment_name = st.secrets["REAL_DEPLOYMENT"]
    token = st.secrets["REAL_APIKEY"]
    base_url = endpoint.replace("https://", "wss://").rstrip("/") + "/openai/v1"

    client = AsyncOpenAI(websocket_base_url=base_url, api_key=token)

    async with client.realtime.connect(model=deployment_name) as connection:
        # 세션 포맷 세팅 (출력은 오디오+텍스트 모두 받음)
        await connection.session.update(
            session={
                "type": "realtime",
                "instructions": "당신은 친절한 AI 도우미입니다. 모든 답변은 한국어로 간결하고 대화하듯이 하세요.",
                "output_modalities": ["audio", "text"], 
                "audio": {
                    # 브라우저 녹음 장치(보통 44.1kHz나 48kHz WebM/WAV) 입력 형식 지정
                    "input": {
                        "transcription": {"model": "whisper-1"},
                        "format": {"type": "audio/pcm", "rate": 24000} # 혹은 서버 내에서 자동 컨버팅 기대
                    },
                    "output": {
                        "voice": "alloy",
                        "format": {"type": "audio/pcm", "rate": 24000},
                    },
                },
            }
        )

        # 1. 브라우저에서 넘어온 오디오 바이너리를 Base64로 인코딩하여 전송
        b64_audio = base64.b64encode(audio_bytes).decode()
        await connection.input_audio_buffer.append(audio=b64_audio)
        
        # 2. 서버에 유저 발화가 끝났음을 알리고 답변 요청
        await connection.input_audio_buffer.commit()
        await connection.response.create()

        user_transcript = ""
        ai_transcript = ""
        ai_audio_chunks = bytearray()

        # 3. 서버 응답 이벤트 수신 루프
        async for event in connection:
            if event.type == "conversation.item.input_audio_transcription.completed":
                user_transcript = event.transcript.strip()
            elif event.type == "response.output_audio_transcript.delta":
                ai_transcript += event.delta
            elif event.type == "response.output_audio.delta":
                ai_audio_chunks.extend(base64.b64decode(event.delta))
            elif event.type == "response.done":
                break

        return user_transcript, ai_transcript, bytes(ai_audio_chunks)

# --- UI 레이아웃 ---

st.write("### 🎛️ 마이크 컨트롤러")
st.write("아래 버튼을 누르고 말씀하신 뒤, 완료되면 다시 눌러주세요.")

# 💡 스트림릿 전용 웹 마이크 컴포넌트 렌더링
audio_result = mic_recorder(
    start_prompt="🔴 녹음 시작",
    stop_prompt="⏹️ 녹음 완료 및 전송",
    key="recorder",
    format="wav" # 브라우저가 WAV 표준 규격으로 녹음하여 전달함
)

# 사용자가 녹음을 완료해서 오디오 데이터가 서버로 입수되었을 때
if audio_result and "bytes" in audio_result:
    with st.spinner("AI가 청취 중..."):
        loop = get_or_create_loop()
        # 비동기 함수 실행 및 결과 도출
        user_text, ai_text, ai_audio = loop.run_until_complete(
            process_voice_chat(audio_result["bytes"])
        )
        
        # 대화 기록 기록
        if user_text or ai_text:
            st.session_state.chat_history.append({
                "user": user_text if user_text else "(음성 인식 오류)",
                "ai": ai_text,
                "ai_audio": ai_audio
            })
            # 오디오 중복 실행 방지를 위해 결과 초기화 처리
            st.rerun()

# 대화창 및 오디오 플레이어 출력
st.write("---")
for chat in reversed(st.session_state.chat_history):
    # 유저 말풍선
    with st.chat_message("user"):
        st.write(chat["user"])
    # AI 말풍선
    with st.chat_message("assistant"):
        st.write(chat["ai"])
        if chat["ai_audio"]:
            # 💡 중요: 스트림릿 웹 플레이어를 통해 브라우저 스피커로 AI의 목소리를 재생합니다!
            st.audio(chat["ai_audio"], format="audio/pcm", sample_rate=24000)
