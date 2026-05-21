# 자동 시험 생성 시스템

강의자료(PDF, PPTX, 영상)를 넣으면 시험 문제랑 모범답안을 자동으로 만들어주는 멀티 에이전트 시스템입니다.

---

## 동작 방식

총 9개의 AI 에이전트가 순서대로 협력합니다.

| 에이전트 | 하는 일 |
|---|---|
| Collector | 강의자료 파일 읽어서 텍스트로 변환 |
| Topic Extractor | 주요 토픽이랑 핵심 개념 추출 |
| Planner | 요구사항 보고 문제 구성 결정 |
| Short Answer / Essay / Application Generator | 각 유형별 문제 생성 (병렬 실행) |
| Answer Generator | 모범답안이랑 채점 기준 작성 |
| Refiner | 교수자 피드백 반영해서 문제 수정 |
| Assembler | 최종 docx 파일로 조립 |

---

## 설치

### ffmpeg (영상 파일 사용 시에만 필요)

```
winget install ffmpeg
```

또는 https://ffmpeg.org/download.html 에서 직접 설치 후 PATH 추가.

### Python 패키지

```
pip install -r requirements.txt
```

Whisper 모델은 첫 실행 시 자동 다운로드됩니다 (약 140MB).

---

## 환경 설정

1. GCP에서 프로젝트 생성 후 Vertex AI API 활성화
2. `.env.example` 참고해서 `.env` 파일 새로 만들고 아래 내용 입력

```
GCP_PROJECT_ID=프로젝트ID
GCP_LOCATION=us-central1
```

3. 인증 설정

```
gcloud auth application-default login
```

---

## 사용 방법

1. `input/` 폴더에 강의자료 넣기 (PDF, PPTX, MP4)
2. `input/requirements.txt`에 요구사항 자유롭게 작성

```
단답형 4개, 에세이형 3개, 응용형 3개. 난이도 중간. 2~7장 범위. 페이지당 문제 1개.
```

3. 실행

```
python main.py
```

4. `output/exam.docx` 확인 후 터미널에서 피드백 입력.
   수정 없으면 엔터 → 최종 파일 생성

---

## 결과물

- `output/exam.docx` — 시험지
- `output/answer_key.docx` — 모범답안 + 채점 기준

---

## 주의사항

- 강의자료 파일은 `input/`에 직접 넣어서 사용하세요 (git에 포함되지 않습니다)
- `.env` 파일은 본인이 직접 생성해야 합니다. `.env.example` 참고
