# 자동 시험 생성 시스템

강의자료를 넣으면 시험지와 모범답안을 자동으로 만들어 주는 프로그램입니다.

PDF, PPT, 영상, 텍스트 파일을 읽고 다음 파일을 만듭니다.

- `output/exam.docx`: 학생에게 나눠 줄 시험지
- `output/answer_key.docx`: 교수자용 모범답안과 채점기준

컴퓨터나 코딩에 익숙하지 않아도 따라할 수 있도록, 아래 순서대로 진행하면 됩니다.

---

## 1. 이 프로그램이 하는 일

이 프로그램은 여러 단계로 시험을 만듭니다.

1. `input/` 폴더에 있는 강의자료를 읽습니다.
2. 강의자료에서 중요한 토픽을 뽑습니다.
3. 각 토픽에 해당하는 강의자료 조각을 찾아 붙입니다.
4. 사용자가 적은 요구사항을 읽고 시험 구성을 정합니다.
5. 진위형, 단답형, 에세이형, 응용형 문제를 만듭니다.
6. 각 문제의 모범답안과 채점기준을 만듭니다.
7. 품질 검토를 하고 필요한 경우 문제를 수정합니다.
8. 최종 Word 파일 두 개를 `output/` 폴더에 저장합니다.

---

## 2. 폴더 설명

자주 만지는 폴더는 세 곳입니다.

| 폴더/파일 | 뜻 |
|---|---|
| `input/` | 강의자료와 시험 요구사항을 넣는 곳 |
| `input/requirements.txt` | 어떤 시험을 만들지 적는 파일 |
| `output/` | 완성된 시험지와 모범답안이 나오는 곳 |

코드를 고치지 않고 사용하는 사람은 보통 `input/`과 `output/`만 보면 됩니다.

---

## 3. 처음 한 번만 준비하기

### 3.1 Python 설치

이 프로그램은 Python으로 실행합니다.

Windows라면 Microsoft Store 또는 Python 공식 사이트에서 Python을 설치하세요.

설치가 끝났는지 확인하려면 터미널에서 아래 명령을 입력합니다.

```bash
python --version
```

버전 숫자가 나오면 설치가 된 것입니다.

### 3.2 필요한 패키지 설치

프로젝트 폴더에서 아래 명령을 실행합니다.

```bash
pip install -r requirements.txt
```

### 3.3 API 키 준비

이 프로그램은 AI 모델을 사용하므로 API 설정이 필요합니다.

중요: 이 프로그램은 **Google Cloud Vertex AI의 Gemini**와 **Claude API**를 함께 사용합니다.

- Gemini(Vertex AI): 시험 계획, 응용형 문제, 모범답안, 채점기준, 품질검토 등에 사용합니다.
- Claude: 강의자료에서 토픽을 뽑고, 단답형/에세이형/진위형 문제를 만드는 데 사용합니다.

기본 설정은 **Google Cloud Vertex AI + Claude API**입니다.

예외적으로 Google Cloud를 쓰지 않을 때만 **Gemini API 키 + Claude API 키** 방식을 사용하세요.

#### 3.3.1 `.env.example`을 복사해서 `.env` 만들기

먼저 `.env.example` 파일을 복사해서 `.env` 파일을 만듭니다.

Windows PowerShell에서는 아래 명령을 사용합니다.

```powershell
Copy-Item .env.example .env
```

macOS나 Linux에서는 아래 명령을 사용합니다.

```bash
cp .env.example .env
```

그다음 새로 생긴 `.env` 파일을 열어서 예시 값을 본인의 실제 값으로 바꿉니다.

기본 형태는 아래와 같습니다.

```env
GCP_PROJECT_ID=본인_Google_Cloud_프로젝트_ID
GCP_LOCATION=us-central1
ANTHROPIC_API_KEY=본인_Claude_API_키
```

`.env.example`에도 같은 구조가 들어 있습니다.

#### 3.3.2 Google Cloud Vertex AI 준비하기

기본 방식에서는 Gemini를 Google Cloud Vertex AI를 통해 사용합니다.

1. Google Cloud에서 프로젝트를 만들거나 기존 프로젝트를 선택합니다.
2. 해당 프로젝트에서 Vertex AI API를 사용 설정합니다.
3. Google Cloud 프로젝트 ID를 복사해서 `.env`의 `GCP_PROJECT_ID`에 넣습니다.
4. 지역은 특별한 이유가 없으면 `GCP_LOCATION=us-central1` 그대로 둡니다.
5. 터미널에서 아래 명령으로 Google Cloud 인증을 합니다.

```bash
gcloud auth application-default login
```

명령을 실행하면 브라우저가 열리고 Google 계정으로 로그인하게 됩니다. 로그인 후 터미널로 돌아오면 이 프로그램이 Vertex AI를 사용할 수 있습니다.

#### 3.3.3 Claude API 키 준비하기

Claude는 Anthropic Console에서 API 키를 발급받아 사용합니다.

Claude API 키는 발급 직후 화면에 한 번만 보이는 경우가 있으므로, 발급하자마자 바로 복사해서 `.env`의 `ANTHROPIC_API_KEY`에 넣어야 합니다.

```env
ANTHROPIC_API_KEY=본인_Claude_API_키
```

키를 잃어버렸다면 기존 키를 삭제하거나 비활성화하고 새 키를 발급받는 편이 안전합니다.

또한 Claude API는 계정 상태, 결제 설정, 사용량 제한에 따라 호출이 막힐 수 있습니다. API 키는 비밀번호처럼 다뤄야 하며, GitHub나 메신저에 올리면 안 됩니다.

#### 3.3.4 예외: Gemini API 키를 쓰는 경우

Google Cloud Vertex AI를 쓰지 않는 경우에는 Gemini API 키를 직접 사용할 수 있습니다.

이 경우 `.env`에서 `GCP_PROJECT_ID`, `GCP_LOCATION`을 지우거나 주석 처리하고, 대신 `GEMINI_API_KEY`를 넣습니다.

```env
GEMINI_API_KEY=본인_Gemini_API_키
ANTHROPIC_API_KEY=본인_Claude_API_키
```

다시 말해 기본은 `GCP_PROJECT_ID`, `GCP_LOCATION`, `ANTHROPIC_API_KEY`이고, 예외적으로만 `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`를 사용합니다.

중요: `.env`에는 개인 인증 정보가 들어가므로 GitHub에 올리면 안 됩니다.

### 3.4 영상 파일을 쓸 경우

영상 파일을 넣으려면 `ffmpeg`가 필요합니다.

Windows에서는 아래 명령으로 설치할 수 있습니다.

```bash
winget install ffmpeg
```

PDF나 PPT만 사용할 경우에는 이 단계가 필요 없습니다.

---

## 4. 시험 만들기

### 4.1 강의자료 넣기

`input/` 폴더에 강의자료를 넣습니다.

사용 가능한 파일 형식:

- `.pdf`
- `.pptx`
- `.ppt`
- `.mp4`
- `.mov`
- `.avi`
- `.mkv`
- `.txt`

예시:

```text
input/
├── requirements.txt
├── lecture1.pdf
├── lecture2.pdf
└── lecture3.pptx
```

### 4.2 requirements.txt 작성하기

`input/requirements.txt` 파일에 원하는 시험 조건을 적습니다.

예시:

```text
TF형 10개. 단답형 5개, 에세이형 3개, 응용형 2개.
난이도는 어렵게.
시험 치는 과목: 한글 - 과학적 관리, 영어 - Scientific Management.
년도 / 학기: 2026학년도 1학기.
기말고사 시험이야.
시험은 4월 14일 9시 30분 ~ 10시 45분에 진행해.
```

프로그램은 자연어로 적힌 요구사항을 읽습니다. 꼭 표처럼 쓰지 않아도 됩니다.

### 4.3 실행하기

프로젝트 폴더에서 아래 명령을 실행합니다.

```bash
python main.py
```

실행 중에는 여러 단계가 터미널에 표시됩니다.

처음 실행하면 시간이 오래 걸릴 수 있습니다. 강의자료가 많거나 문제 수가 많으면 더 오래 걸립니다.

---

## 5. 결과 확인하기

실행이 끝나면 `output/` 폴더에 파일이 생깁니다.

```text
output/
├── exam.docx
└── answer_key.docx
```

각 파일의 뜻은 다음과 같습니다.

| 파일 | 뜻 |
|---|---|
| `exam.docx` | 학생용 시험지 |
| `answer_key.docx` | 교수자용 모범답안, 정답, 채점기준 |

프로그램은 중간에 파일을 확인하라고 멈출 수 있습니다.

이때 Word 파일을 열어서 확인한 뒤, 터미널에서 Enter를 누르면 됩니다.

수정할 문제가 있으면 아래 형식으로 입력할 수 있습니다.

```text
Q3: 문제가 너무 모호하니 더 구체적으로 바꿔줘
Q7: 답이 강의자료와 맞지 않으니 다시 수정해줘
```

수정할 것이 없으면 아무것도 입력하지 않고 Enter를 누르면 종료됩니다.

---

## 6. 문제 유형

이 프로그램은 네 가지 문제 유형을 지원합니다.

| 유형 | 설명 |
|---|---|
| 진위형 | T/F로 답하는 문제 |
| 단답형 | 단어 또는 짧은 구로 답하는 문제 |
| 에세이형 | 설명, 비교, 절차, 분석을 요구하는 문제 |
| 응용형 | 강의 개념이나 프레임워크를 새로운 상황에 적용하는 문제 |

최근 구조에서는 단답형과 진위형은 문제를 만들 때 정답도 함께 만들고, 그 정답을 모범답안 생성 단계로 넘깁니다.

에세이형과 응용형은 강의자료에서 해당 토픽과 관련된 텍스트 조각을 함께 넘겨 모범답안이 너무 일반적으로 작성되지 않게 합니다.

---

## 7. 내부 작동 방식

프로그램 내부에는 여러 에이전트가 있습니다.

| 에이전트 | 역할 |
|---|---|
| `collector` | 강의자료 파일을 읽어서 텍스트로 바꿈 |
| `topic_extractor` | Claude를 사용해 강의자료에서 주요 토픽과 핵심 개념을 뽑음 |
| `topic_slicer` | 전체 강의 텍스트에서 각 토픽과 관련된 조각을 찾아 붙임 |
| `planner` | 요구사항을 읽고 문제 수, 난이도, 문제 유형 배치를 정함 |
| `generators` | Claude와 Gemini를 사용해 진위형, 단답형, 에세이형, 응용형 문제를 만듦 |
| `answer_generator` | Gemini를 사용해 정답, 모범답안, 채점기준을 만듦 |
| `quality_reviewer` | Gemini를 사용해 문제 형식과 품질을 검토함 |
| `refiner` | Gemini를 사용해 지적된 문제를 수정함 |
| `assembler` | 최종 Word 파일을 만듦 |

대략적인 흐름은 다음과 같습니다.

```text
input 자료
→ collector
→ topic_extractor
→ topic_slicer
→ planner
→ 문제 생성
→ 답안 생성
→ 품질 검토
→ Word 파일 생성
```

---

## 8. API 오류가 날 때

가끔 `429`, `500`, `503` 같은 API 오류가 날 수 있습니다.

이 오류는 Gemini에서 날 수도 있고 Claude에서 날 수도 있습니다.

터미널에 `[Gemini API]`라고 나오면 Gemini 쪽 오류입니다.

터미널에 `[Claude API]`라고 나오면 Claude 쪽 오류입니다.

이 뜻은 보통 다음 중 하나입니다.

| 오류 | 쉬운 설명 |
|---|---|
| `429` | 너무 많은 요청을 한 번에 보냈거나 사용량 제한에 걸림 |
| `500` | API 서버 쪽 일시 오류 |
| `503` | API 서버가 잠시 바쁘거나 사용할 수 없음 |

해결 방법:

1. 잠시 기다렸다가 다시 실행합니다.
2. 문제 수를 줄여 봅니다.
3. 강의자료 수를 줄여 봅니다.
4. 같은 시간에 여러 번 실행하지 않습니다.

프로그램에는 일부 재시도 로직이 들어 있지만, API 사용량 제한 자체를 완전히 없앨 수는 없습니다.

Claude 쪽에서 오류가 나면 토픽 추출이나 문제 생성 단계가 멈출 수 있습니다.

Gemini 쪽에서 오류가 나면 시험 계획, 응용형 문제, 답안 생성, 품질검토, 수정 단계가 멈출 수 있습니다.

---

## 9. 자주 생기는 문제

### output 폴더에 파일이 없어요

`python main.py`를 실행했는지 확인하세요.

또 `input/requirements.txt`와 강의자료 파일이 있는지 확인하세요.

### input 폴더에 뭘 넣어야 하나요

강의자료와 `requirements.txt`를 넣으면 됩니다.

예:

```text
input/과학적관리_1주차.pdf
input/과학적관리_2주차.pdf
input/requirements.txt
```

### API 키 오류가 나요

`.env` 파일이 있는지 확인하세요.

기본 설정은 아래 세 값입니다.

```env
GCP_PROJECT_ID=...
GCP_LOCATION=us-central1
ANTHROPIC_API_KEY=...
```

Google Cloud Vertex AI를 쓰지 않는 예외적인 경우에는 아래처럼 설정합니다.

```env
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
```

즉, Gemini 쪽 설정만 있거나 Claude 쪽 설정만 있으면 전체 파이프라인이 끝까지 돌지 않습니다.

### 영상 파일을 읽지 못해요

`ffmpeg`가 설치되어 있는지 확인하세요.

```bash
ffmpeg -version
```

버전 정보가 나오지 않으면 ffmpeg가 설치되지 않았거나 PATH에 등록되지 않은 것입니다.

---

## 10. 개발자를 위한 명령

테스트 실행:

```bash
python -m pytest
```

특정 테스트만 실행:

```bash
python -m pytest tests/test_agents.py -q
```

현재 변경 확인:

```bash
git status
```

---

## 11. 주의사항

- `.env` 파일은 절대 공유하지 마세요.
- `input/`에 넣은 강의자료는 저작권이 있을 수 있으니 외부에 올리지 마세요.
- AI가 만든 시험과 답안은 반드시 사람이 한 번 확인해야 합니다.
- API 사용량에 따라 비용이 발생할 수 있습니다.
- 생성 결과가 마음에 들지 않으면 `requirements.txt`의 요구사항을 더 구체적으로 적어 보세요.

---

## 12. 아주 짧은 사용 순서

정말 짧게 말하면 아래 순서입니다.

1. `input/` 폴더에 강의자료를 넣습니다.
2. `input/requirements.txt`에 시험 조건을 적습니다.
3. `.env`에 API 키를 넣습니다.
4. 터미널에서 실행합니다.

```bash
python main.py
```

5. `output/exam.docx`와 `output/answer_key.docx`를 확인합니다.
