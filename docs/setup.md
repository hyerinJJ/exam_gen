# 환경 설정

## 기본 방식 — Google Cloud Vertex AI + Claude API

현재 파이프라인은 Gemini와 Claude를 함께 사용합니다.

- Gemini: planner, application generator, answer generator, quality reviewer, refiner
- Claude: topic_extractor, short/essay/tf generator

먼저 `.env.example`을 복사해 `.env`를 만듭니다.

```bash
cp .env.example .env
```

기본 `.env` 형태:

```env
GCP_PROJECT_ID=your-google-cloud-project-id
GCP_LOCATION=us-central1
ANTHROPIC_API_KEY=your-anthropic-api-key
```

Google Cloud Vertex AI를 쓰려면 프로젝트에서 Vertex AI API를 활성화하고, 아래 인증을 한 번 실행합니다.

```bash
gcloud auth application-default login
```

Claude API 키는 Anthropic Console에서 발급받아 `ANTHROPIC_API_KEY`에 넣습니다. 발급 직후 한 번만 보일 수 있으니 바로 복사해 두는 것이 안전합니다.

## 예외 방식 — Gemini API 키 + Claude API

Google Cloud Vertex AI를 쓰지 않는 경우에는 `GCP_PROJECT_ID`, `GCP_LOCATION` 대신 Gemini API 키를 사용합니다.

```env
GEMINI_API_KEY=your-gemini-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
```

## 실행

```bash
pip install -r package_requirements.txt
python main.py
```

## 입력 파일

- 강의자료: `input/` 폴더
- 시험 요구사항: `input/requirements.txt`
- 패키지 설치 목록: `package_requirements.txt`

루트의 패키지 설치 목록과 `input/requirements.txt`는 서로 다른 파일입니다.
