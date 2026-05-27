import os
import io
import base64
import asyncio
import streamlit as st
from openai import AsyncOpenAI
from pydub import AudioSegment
from streamlit_mic_recorder import mic_recorder

# 1. 페이지 설정 및 UI 구성
st.set_page_config(page_title="Azure Realtime Voice Chat", page_icon="🎙️", layout="centered")
st.title("🎙️ Azure Realtime 웹 음성 비서")
st.caption("웹 브라우저의 마이크를 이용해 대화하는 챗봇입니다.")

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

# 2. 오디오 규격 변환 및 Azure Realtime API 통신 함수
async def process_voice_chat(audio_bytes):
    # Streamlit Secrets에서 보안 환경 변수 로드
    endpoint = st.secrets["REAL_ENDPOINT"]
    deployment_name = st.secrets["REAL_DEPLOYMENT"]
    token = st.secrets["REAL_APIKEY"]
    base_url = endpoint.replace("https://", "wss://").rstrip("/") + "/openai/v1"

    client = AsyncOpenAI(websocket_base_url=base_url, api_key=token)

    # 💡 [무한 로딩 해결 핵심] 브라우저의 WAV 바이너리를 Azure 표준(PCM 24kHz, Mono)으로 변환
    try:
        audio_stream = io.BytesIO(audio_bytes)
        sound = AudioSegment.from_file(audio_stream, format="wav")
        # 24000Hz, 모노(1채널)로 변환 후 날것의 PCM 바이트 데이터 추출
        sound = sound.set_frame_rate(24000).set_channels(1)
        pcm_payload = sound.raw_data  # 헤더가 제거된 순수 PCM 데이터
    except Exception as e:
        st.error(f"오디오 변환 실패: {e}")
        return "오디오 변환 실패", "오디오 변환 실패", b""

    async with client.realtime.connect(model=deployment_name) as connection:
        # 세션 포맷 세팅 (인풋 포맷을 변환 규격인 pcm 24kHz로 지정)
        await connection.session.update(
            session={
                "type": "realtime",
                "instructions": "당신은 친절한 AI 도우미입니다. 모든 답변은 한국어로 간결하고 대화하듯이 친숙하게 하세요.",
                "output_modalities": ["audio", "text"], 
                "audio": {
                    "input": {
                        "transcription": {"model": "whisper-1"},
                        "format": {"type": "audio/pcm", "rate": 24000}
                    },
                    "output": {
                        "voice": "alloy",
                        "format": {"type": "audio/pcm", "rate": 24000},
                    },
                },
            }
        )

        # 변환이 완료된 순수 PCM 데이터를 Base64로 인코딩하여 전송
        b64_audio = base64.b64encode(pcm_payload).decode()
        await connection.input_audio_buffer.append(audio=b64_audio)
        
        # 서버에 오디오 입력이 끝났음을 전송하고 대답 트리거
        await connection.input_audio_buffer.commit()
        await connection.response.create()

        user_transcript = ""
        ai_transcript = ""
        ai_audio_chunks = bytearray()

        # 서버 응답 이벤트 수신 루프 (규격이 맞기 때문에 무한 로딩 없이 통과됩니다)
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

# --- UI 레이아웃 화면 구성 ---

st.write("### 🎛️ 마이크 컨트롤러")
st.write("아래 버튼을 누르고 말씀하신 뒤, 완료되면 다시 눌러주세요.")

# 스트림릿 전용 웹 마이크 컴포넌트 렌더링
audio_result = mic_recorder(
    start_prompt="🔴 녹음 시작",
    stop_prompt="⏹️ 녹음 완료 및 전송",
    key="recorder",
    format="wav"
)

# 사용자가 녹음을 완료하여 오디오 데이터가 웹 서버로 입수되었을 때
if audio_result and "bytes" in audio_result:
    with st.spinner("AI가 청취 중..."):
        loop = get_or_create_loop()
        # 비동기 함수 실행 및 결과 도출
        user_text, ai_text, ai_audio = loop.run_until_complete(
            process_voice_chat(audio_result["bytes"])
        )
        
        # 정상적으로 변환된 대화 텍스트가 있다면 세션에 기록
        if user_text or ai_text:
            st.session_state.chat_history.append({
                "user": user_text if user_text else "(음성 인식 완료)",
                "ai": ai_text,
                "ai_audio": ai_audio
            })
            # 오디오 무한 중복 처리를 방지하기 위해 화면 리프레시
            st.rerun()

# 대화창 및 오디오 플레이어 출력 (최신 대화가 아래로 가도록 순서대로 출력)
st.write("---")
for chat in st.session_state.chat_history:
    # 유저 말풍선
    with st.chat_message("user"):
        st.write(chat["user"])
    # AI 말풍선
    with st.chat_message("assistant"):
        st.write(chat["ai"])
        if chat["ai_audio"]:
            # 스트림릿 플레이어를 통해 브라우저 스피커로 AI의 정속 목소리를 재생합니다.
            st.audio(chat["ai_audio"], format="audio/pcm", sample_rate=24000)
