import os
import re
from PIL import Image
from pypdf import PdfReader
import pytesseract
import streamlit as st

st.set_page_config(
    page_title="하나투어 대리점 수신 게시글 TSV 변환기", layout="wide"
)

st.title("📄 하나투어 대리점 수신 게시글 TSV 교차검증 변환기")
st.caption(
    "대표자명, 사업자번호, 주소 항목만 첨부파일들과 비교하여 불일치 시 'X' 표시합니다."
)


def extract_files_text(uploaded_files):
    combined_text = ""
    for file in uploaded_files:
        ext = os.path.splitext(file.name)[1].lower()
        try:
            if ext == ".txt":
                combined_text += (
                    file.read().decode("utf-8", errors="ignore") + "\n"
                )
            elif ext == ".pdf":
                reader = PdfReader(file)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        combined_text += extracted + "\n"
            elif ext in [".png", ".jpg", ".jpeg", ".bmp"]:
                img = Image.open(file)
                combined_text += (
                    pytesseract.image_to_string(img, lang="kor+eng") + "\n"
                )
        except Exception as e:
            st.error(f"'{file.name}' 읽기 오류: {e}")
    return combined_text


def parse_post(post_text, file_text=""):
    headers = [
        "유형",
        "게시글 번호",
        "A코드",
        "대리점명",
        "대표자명",
        "영업팀",
        "하나A",
        "핸드폰번호",
        "사업자번호",
        "관광사업자번호",
        "법인 번호",
        "전화번호",
        "팩스번호",
        "이메일주소",
        "주소",
        "계좌번호",
        "DTI",
        "업태",
        "업종",
        "거래재개",
    ]

    data = {h: "" for h in headers}

    post_no_match = re.search(r"^(\d{7})\.", post_text, re.MULTILINE)
    if post_no_match:
        data["게시글 번호"] = post_no_match.group(1)

    title_match = re.search(
        r"^\d{7}\.\s*([^\n/]+)\s*/\s*([^\n/]+)\s*/\s*([^\n]+)",
        post_text,
        re.MULTILINE,
    )
    if title_match:
        data["대리점명"] = title_match.group(1).strip()
        team_person = title_match.group(2).strip()
        tp_match = re.match(r"(.+?팀)\s*(.+)", team_person)
        if tp_match:
            data["영업팀"] = tp_match.group(1).strip()
            data["하나A"] = tp_match.group(2).strip()
        else:
            data["영업팀"] = team_person
        data["유형"] = title_match.group(3).strip()

    patterns = {
        "A코드": r"1\.\s*A코드[^\n:]*[:\s]*([^\n]+)",
        "대리점명_본문": r"2\.\s*상호명[^\n:]*[:\s]*([^\n]+)",
        "대표자명": r"3\.\s*대표자\s*이름[^\n:]*[:\s]*([^\n]+)",
        "사업자번호": r"5\.\s*사업자등록번호[^\n:]*[:\s]*([^\n]+)",
        "전화번호": r"6\.\s*사업장\s*대표\s*전화번호[^\n:]*[:\s]*([^\n]+)",
        "팩스번호": r"7\.\s*사업장\s*FAX[^\n:]*[:\s]*([^\n]+)",
        "이메일주소": r"8\.\s*이메일\s*주소[^\n:]*[:\s]*([^\n]+)",
        "주소": r"11\.\s*도로명\s*주소[^\n:]*[:\s]*([^\n]+)",
        "DTI": r"12\.\s*계산서발행구분[^\n:]*[:\s]*([^\n]+)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, post_text)
        if match:
            val = match.group(1).strip()
            if val in ["없음", "X", "x", "-", "None"]:
                val = ""
            if key == "대리점명_본문" and not data["대리점명"]:
                data["대리점명"] = val
            elif key == "A코드":
                val_clean = re.sub(
                    r"신규\s*생성|\(택\s*1\)", "", val, flags=re.IGNORECASE
                ).strip()
                data["A코드"] = val_clean
            elif key != "대리점명_본문":
                data[key] = val

    if "자사" in data["DTI"]:
        data["DTI"] = "자사"
    elif "타사" in data["DTI"]:
        data["DTI"] = "타사"

    # 첨부파일이 있는 경우: 대표자명, 사업자번호, 주소 3개 항목만 검증
    if file_text.strip():
        clean_file_text = re.sub(r"\s+", "", file_text)
        verify_keys = ["대표자명", "사업자번호", "주소"]

        for key in verify_keys:
            val = data[key]
            if val:
                clean_val = re.sub(r"[\s\-]", "", val)
                # 도로명 주소의 경우 핵심 번기/도로명 위주 비교를 위해 특수문자 제거 후 검색
                if clean_val not in clean_file_text:
                    data[key] = "X"

    return data, headers


col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 첨부파일 업로드 (여러 개 가능)")
    uploaded_files = st.file_uploader(
        "PDF, 이미지, TXT 파일을 여러 개 선택하거나 한번에 드래그하세요.",
        type=["pdf", "png", "jpg", "jpeg", "txt"],
        accept_multiple_files=True,
    )

with col2:
    st.subheader("2. 게시글 본문 입력 (필수)")
    post_text = st.text_area(
        "게시글 텍스트를 복사해서 붙여넣으세요.", height=200
    )

if st.button("🔍 교차검증 및 TSV 데이터 생성", type="primary"):
    if not post_text.strip():
        st.warning("게시글 본문 텍스트를 입력해 주세요.")
    else:
        file_text = ""
        if uploaded_files:
            file_text = extract_files_text(uploaded_files)

        parsed, headers = parse_post(post_text, file_text)
        row = [parsed.get(h, "") for h in headers]

        tsv_output = "\t".join(headers) + "\n" + "\t".join(row)

        st.success("변환 및 교차검증이 완료되었습니다!")

        st.subheader("3. 결과 (복사하여 엑셀에 Ctrl+V 하세요)")
        st.text_area("TSV 결과", value=tsv_output, height=100)
