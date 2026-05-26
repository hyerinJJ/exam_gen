# tests/test_tools.py
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── read_file 라우터 분기 테스트 (모의 객체 사용) ─────────────────────────────

def test_read_file_routes_pdf(tmp_path):
    f = tmp_path / "test.pdf"
    f.write_bytes(b"%PDF-1.4")
    with patch("tools.file_readers.read_pdf", return_value="pdf text") as mock_pdf:
        from tools.file_readers import read_file
        result = read_file(str(f))
    mock_pdf.assert_called_once()
    assert result == "pdf text"


def test_read_file_routes_pptx(tmp_path):
    f = tmp_path / "test.pptx"
    f.write_bytes(b"PK")  # zip stub
    with patch("tools.file_readers.read_pptx", return_value="pptx text") as mock_pptx:
        from tools.file_readers import read_file
        result = read_file(str(f))
    mock_pptx.assert_called_once()
    assert result == "pptx text"


@pytest.mark.parametrize("ext", [".mp4", ".mov", ".avi", ".mkv"])
def test_read_file_routes_video_extensions(tmp_path, ext):
    f = tmp_path / f"test{ext}"
    f.write_bytes(b"\x00")
    with patch("tools.file_readers.read_video", return_value="video text") as mock_vid:
        from tools.file_readers import read_file
        result = read_file(str(f))
    mock_vid.assert_called_once()
    assert result == "video text"


def test_read_file_routes_txt(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world", encoding="utf-8")
    from tools.file_readers import read_file
    assert read_file(str(f)) == "hello world"


def test_read_file_raises_for_missing_file(tmp_path):
    from tools.file_readers import read_file
    with pytest.raises(FileNotFoundError):
        read_file(str(tmp_path / "nonexistent.mp4"))


def test_read_file_raises_for_unsupported_extension(tmp_path):
    f = tmp_path / "test.xyz"
    f.write_bytes(b"\x00")
    from tools.file_readers import read_file
    with pytest.raises(ValueError, match="지원하지 않는"):
        read_file(str(f))


# ── ffmpeg 체크 테스트 ────────────────────────────────────────────────────────

def test_check_ffmpeg_ok():
    """시스템에 ffmpeg가 설치되어 있으면 예외 없이 통과해야 함."""
    from tools.file_readers import _check_ffmpeg
    _check_ffmpeg()  # 예외 없으면 통과


def test_check_ffmpeg_not_found_raises():
    """ffmpeg가 없으면 RuntimeError를 발생시켜야 함."""
    from tools.file_readers import _check_ffmpeg
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="ffmpeg"):
            _check_ffmpeg()


# ── read_video 단위 테스트 (whisper mock) ─────────────────────────────────────

def test_read_video_returns_text(tmp_path):
    """read_video가 whisper 결과 text 문자열을 반환해야 함."""
    fake_video = tmp_path / "lecture.mp4"
    fake_video.write_bytes(b"\x00" * 16)

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": "  강의 내용입니다.  "}

    with patch("tools.file_readers._check_ffmpeg"), \
         patch("shutil.copy2"), \
         patch("whisper.load_model", return_value=mock_model):
        from tools.file_readers import read_video
        result = read_video(fake_video)

    assert result == "  강의 내용입니다.  "
    mock_model.transcribe.assert_called_once()


def test_read_video_temp_file_cleaned_up(tmp_path):
    """임시 파일이 transcribe 후 삭제되어야 함."""
    fake_video = tmp_path / "lecture.mp4"
    fake_video.write_bytes(b"\x00" * 16)

    created_tmp: list = []

    def capture_copy(src, dst):
        created_tmp.append(Path(dst))

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": ""}

    with patch("tools.file_readers._check_ffmpeg"), \
         patch("shutil.copy2", side_effect=capture_copy), \
         patch("whisper.load_model", return_value=mock_model):
        from tools.file_readers import read_video
        read_video(fake_video)

    assert created_tmp, "copy2가 한 번도 호출되지 않음"
    assert not created_tmp[0].exists(), f"임시 파일이 삭제되지 않음: {created_tmp[0]}"


def test_read_video_temp_cleaned_up_on_error(tmp_path):
    """transcribe 중 예외가 발생해도 임시 파일이 삭제되어야 함."""
    fake_video = tmp_path / "lecture.mp4"
    fake_video.write_bytes(b"\x00" * 16)

    created_tmp: list = []

    def capture_copy(src, dst):
        created_tmp.append(Path(dst))
        Path(dst).write_bytes(b"\x00")  # 실제로 파일을 만들어야 cleanup이 의미 있음

    mock_model = MagicMock()
    mock_model.transcribe.side_effect = RuntimeError("transcribe 실패")

    with patch("tools.file_readers._check_ffmpeg"), \
         patch("shutil.copy2", side_effect=capture_copy), \
         patch("whisper.load_model", return_value=mock_model):
        from tools.file_readers import read_video
        with pytest.raises(RuntimeError, match="transcribe 실패"):
            read_video(fake_video)

    assert not created_tmp[0].exists(), "예외 발생 시에도 임시 파일이 삭제되어야 함"


# ── 실제 파이프라인 통합 테스트 (ffmpeg로 테스트 영상 생성) ────────────────────

def _make_silent_mp4(output_path: Path, duration: int = 2) -> bool:
    """ffmpeg로 짧은 무음 MP4를 생성. 실패 시 False 반환."""
    ret = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=black:s=64x64:r=1:d={duration}",
            "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono",
            "-t", str(duration),
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest", str(output_path),
        ],
        capture_output=True,
    )
    return ret.returncode == 0 and output_path.exists()


@pytest.mark.slow
def test_read_video_real_pipeline(tmp_path):
    """실제 ffmpeg + whisper로 2초 무음 영상을 처리하는 통합 테스트."""
    video_path = tmp_path / "silent_test.mp4"
    if not _make_silent_mp4(video_path):
        pytest.skip("ffmpeg로 테스트 영상 생성 실패 — 환경 확인 필요")

    from tools.file_readers import read_video
    result = read_video(video_path)

    assert isinstance(result, str), "반환값이 문자열이어야 함"
    print(f"\n[통합 테스트] whisper 출력: {result!r}")
