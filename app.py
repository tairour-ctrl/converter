import os
import re
from PIL import Image
from pypdf import PdfReader
import pytesseract
import streamlit as st

st.set_page_config(
    page_title="하나투어 대리점 수신 게시글 TSV 변환기", layout="wide"
)

st.title("📄 하나투어 대리점 수신 게시글 TSV 변환기")
st.caption(
    "게시글 본문과 첨부파일(사업자등록증 등)에서 정보를 정확히 추출합니다."
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

    # 1. 게시글 번호
    post_no_match = re.search(r"^(\d{7})\.", post_text, re.MULTILINE)
    if post_no_match:
        data["게시글 번호"] = post_no_match.group(1)

    # 2. 제목 (대리점명 / 영업팀 하나A / 유형)
    title_match = re.search(
        r"^\d{7}\.\s*([^\n/]+)\s*/\s*([^\n/]+)\s*/\s*([^\n]+)",
        post_text,
        re.MULTILINE,
    )
    if title_match:
        data["대리점명"] = title_match.group(1).strip()
        team_person = title_match.group(2).strip()

        tp_match = re.search(
            r"([가-힇0-9A-Za-z]+팀)\s*([가-힇A-Za-z]{2,5})", team_person
        )
        if tp_match:
            data["영업팀"] = tp_match.group(1).strip()
            data["하나A"] = tp_match.group(2).strip()
        else:
            data["영업팀"] = team_person

        data["유형"] = title_match.group(3).strip()

    # 3. 영업팀 / 하나A 본문 보완
    if not data["영업팀"] or not data["하나A"]:
        body_tp = re.search(
            r"([가-힇0-9A-Za-z]+팀)\s*([가-힇A-Za-z]{2,5})", post_text
        )
        if body_tp:
            if not data["영업팀"]:
                data["영업팀"] = body_tp.group(1).strip()
            if not data["하나A"]:
                data["하나A"] = body_tp.group(2).strip()

    # 4. A코드 추출 (A+숫자4자리 또는 PH+숫자5자리 영문자 포함 통째로 추출)
    a_code_match = re.search(
        r"(A\d{4}|PH\d{5})", post_text, re.IGNORECASE
    )
    if a_code_match:
        data["A코드"] = a_code_match.group(1).upper()
    else:
        data["A코드"] = ""

    # 5. 본문 주요 패턴 추출
    patterns = {
        "대리점명_본문": r"(?:2\.\s*상호명|상호명|상호)[^\n:]*[:\s]*([^\n]+)",
        "대표자명": r"(?:3\.\s*대표자\s*이름|대표자\s*성명|대표자|성명)[^\n:]*[:\s]*([가-힇]{2,5})",
        "사업자번호": r"(?:5\.\s*사업자등록번호|사업자등록번호|사업자번호)[^\n:]*[:\s]*([^\n]+)",
        "법인 번호": r"(?:10\.\s*법인등록번호|법인등록번호|법인번호)[^\n:]*[:\s]*([^\n]+)",
        "전화번호": r"(?:6\.\s*사업장\s*대표\s*전화번호|전화번호|TEL)[^\n:]*[:\s]*([^\n]+)",
        "팩스번호": r"(?:7\.\s*사업장\s*FAX|팩스번호|FAX)[^\n:]*[:\s]*([^\n]+)",
        "이메일주소": r"(?:8\.\s*이메일\s*주소|이메일)[^\n:]*[:\s]*([^\n]+)",
        "주소": r"(?:11\.\s*도로명\s*주소|도로명\s*주소|주소|소재지)[^\n:]*[:\s]*([^\n]+)",
        "DTI": r"(?:12\.\s*계산서발행구분|계산서발행구분)[^\n:]*[:\s]*([^\n]+)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, post_text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            if val in ["없음", "X", "x", "-", "None"]:
                val = ""
            if key == "대리점명_본문" and not data["대리점명"]:
                data["대리점명"] = val
            elif key != "대리점명_본문":
                data[key] = val

    if "자사" in data["DTI"]:
        data["DTI"] = "자사"
    elif "타사" in data["DTI"]:
        data["DTI"] = "타사"

    # 핸드폰번호 및 계좌번호 수기 작성을 위한 공란 처리
    data["핸드폰번호"] = ""
    data["계좌번호"] = ""

    # 6. 첨부파일(사업자등록증 등)이 업로드된 경우 추출값 보완
    if file_text.strip():
        # 사업자등록번호 추출 (xxx-xx-xxxxx)
        biz_match = re.search(r"\d{3}\s*-\s*\d{2}\s*-\s*\d{5}", file_text)
        if biz_match:
            data["사업자번호"] = re.sub(r"\s+", "", biz_match.group(0))

        # 법인등록번호 추출 (xxxxxx-xxxxxxx)
        corp_match = re.search(r"\d{6}\s*-\s*\d{7}", file_text)
        if corp_match:
            data["법인 번호"] = re.sub(r"\s+", "", corp_match.group(0))

        # 대표자명 추출 (성명/대표자 키워드 뒤 한글 이름)
        rep_match = re.search(
            r"(?:성\s*명|대\s*표\s*자)\s*[:\s]*([가-힇]{2,5})", file_text
        )
        if rep_match:
            data["대표자명"] = rep_match.group(1).strip()

        # 주소(소재지) 추출
        addr_match = re.search(
            r"(?:소\s*재\s*지|주\s*소)[^\n:]*[:\s]*([^\n]+)", file_text
        )
        if addr_match:
            addr_val = addr_match.group(1).strip()
            if len(addr_val) > 5:
                data["주소"] = addr_val

    return data, headers


col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 첨부파일 업로드 (사업자등록증 등)")
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

if st.button("🔍 데이터 추출 및 TSV 생성", type="primary"):
    if not post_text.strip():
        st.warning("게시글 본문 텍스트를 입력해 주세요.")
    else:
        file_text = ""
        if uploaded_files:
            file_text = extract_files_text(uploaded_files)

        parsed, headers = parse_post(post_text, file_text)
        row = [parsed.get(h, "") for h in headers]

        tsv_output = "\t".join(headers) + "\n" + "\t".join(row)

        st.success("데이터 추출 및 변환이 완료되었습니다!")

        st.subheader("3. 결과 (복사하여 엑셀에 Ctrl+V 하세요)")
        st.text_area("TSV 결과", value=tsv_output, height=100)
