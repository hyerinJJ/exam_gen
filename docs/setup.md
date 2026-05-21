# 환경 설정

## 방법 A — AI Studio (간단, 추천)
1. https://aistudio.google.com → Get API key
2. .env에 GEMINI_API_KEY=발급받은키

## 방법 B — Vertex AI (수업 환경)
1. https://cloud.google.com → 프로젝트 생성
2. Vertex AI API 활성화
3. .env에 GCP_PROJECT_ID=프로젝트ID

## 실행
```bash
cp .env.example .env   # .env 파일 생성 후 키 입력
pip install -r requirements.txt
python main.py
```

## 비용
- 개발/테스트: AI Studio 무료 티어 (1,500 req/day)
- 운영: Flash-Lite $0.10/$0.40, Flash $0.30/$2.50 per 1M tokens
- 시험지 한 세트 생성 예상: ~$0.01~0.03
