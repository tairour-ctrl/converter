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


# ─────────────────────────────────────────────
# OCR 전처리 (cv2 없이 Pillow만 사용 → Streamlit Cloud 배포 안정)
# 그레이스케일 → 2배 업스케일 → Otsu 자동 임계값 이진화
# ※ 고정 임계값이 아닌 히스토그램 기반 Otsu라 조명 편차에 강함
# ─────────────────────────────────────────────
def _otsu_threshold(gray_img):
    hist = gray_img.histogram()[:256]
    total = sum(hist)
    if total == 0:
        return 127
    sum_all = sum(i * hist[i] for i in range(256))
    sum_b, w_b, max_var, thr = 0, 0, 0, 127
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var, thr = var, t
    return thr


def preprocess_for_ocr(img):
    g = img.convert("L")  # 그레이스케일
    g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)  # 2배 업스케일
    thr = _otsu_threshold(g)  # Otsu 자동 임계값
    return g.point(lambda x: 0 if x < thr else 255, mode="1")  # 이진화


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
                processed = preprocess_for_ocr(img)
                # 표/블록 문서에는 psm 6 이 psm 3(기본)보다 안정적
                combined_text += (
                    pytesseract.image_to_string(
                        processed, lang="kor+eng", config="--psm 6"
                    )
                    + "\n"
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
            r"([가-힣0-9A-Za-z]+팀)\s*([가-힣A-Za-z]{2,5})", team_person
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
            r"([가-힣0-9A-Za-z]+팀)\s*([가-힣A-Za-z]{2,5})", post_text
        )
        if body_tp:
            if not data["영업팀"]:
                data["영업팀"] = body_tp.group(1).strip()
            if not data["하나A"]:
                data["하나A"] = body_tp.group(2).strip()

    # 4. A코드 추출 (A+숫자4자리 또는 PH+숫자5자리)
    a_code_match = re.search(r"(A\d{4}|PH\d{5})", post_text, re.IGNORECASE)
    if a_code_match:
        data["A코드"] = a_code_match.group(1).upper()
    else:
        data["A코드"] = ""

    # 5. 본문 주요 패턴 추출
    #    - '주소': 제네릭 '주소' 토큰 제거(→ '이메일 주소' 오매칭 방지),
    #             구체 라벨만 사용 + 다음 번호항목 전까지 여러 줄 캡처
    #    - '업태' / '업종': 신규 추가
    patterns = {
        "대리점명_본문": r"(?:2\.\s*상호명|상호명|상호)[^\n:]*[:\s]*([^\n]+)",
        "사업자번호": r"(?:5\.\s*사업자등록번호|사업자등록번호|사업자번호)[^\n:]*[:\s]*([^\n]+)",
        "법인 번호": r"(?:10\.\s*법인등록번호|법인등록번호|법인번호)[^\n:]*[:\s]*([^\n]+)",
        "전화번호": r"(?:6\.\s*사업장\s*대표\s*전화번호|전화번호|TEL)[^\n:]*[:\s]*([^\n]+)",
        "팩스번호": r"(?:7\.\s*사업장\s*FAX|팩스번호|FAX)[^\n:]*[:\s]*([^\n]+)",
        "이메일주소": r"(?:8\.\s*이메일\s*주소|이메일)[^\n:]*[:\s]*([^\n]+)",
        "주소": r"(?:11\.\s*도로명\s*주소|도로명\s*주소|지번\s*주소|사업장\s*소재지|소\s*재\s*지)\s*[:\s]*(.+?)(?=\n\s*\d{1,2}\.|\Z)",
        "DTI": r"(?:12\.\s*계산서발행구분|계산서발행구분)[^\n:]*[:\s]*([^\n]+)",
        "업태": r"(?:9\.\s*업태|업\s*태)\s*[:\s]*([^\n종]+)",
        "업종": r"(?:업\s*종|종\s*목|종\s*류)\s*[:\s]*([^\n]+)",
    }

    for key, pattern in patterns.items():
        flags = re.IGNORECASE | (re.DOTALL if key == "주소" else 0)
        match = re.search(pattern, post_text, flags)
        if match:
            # 줄바꿈·중복 공백 정리 (여러 줄 주소를 한 줄로 병합)
            val = re.sub(r"\s+", " ", match.group(1)).strip()
            if val in ["없음", "X", "x", "-", "None"]:
                val = ""
            if key == "대리점명_본문" and not data["대리점명"]:
                data["대리점명"] = val
            elif key != "대리점명_본문":
                data[key] = val

    # 대표자명 정밀 추출 (공개/비공개 등 제외)
    rep_matches = re.findall(
        r"(?:대표자|성명|대표자\s*이름|대표자\s*성명)[^\n:]*[:\s]*([가-힣A-Za-z\s]+)",
        post_text,
        re.IGNORECASE,
    )
    for rep in rep_matches:
        cleaned_rep = re.sub(
            r"공개|비공개|요청|$개인정보$|[^\n가-힣A-Za-z]", "", rep
        ).strip()
        if len(cleaned_rep) >= 2:
            data["대표자명"] = cleaned_rep
            break

    if "자사" in data["DTI"]:
        data["DTI"] = "자사"
    elif "타사" in data["DTI"]:
        data["DTI"] = "타사"

    # 핸드폰번호 및 계좌번호는 수기 작성을 위한 공란 처리
    data["핸드폰번호"] = ""
    data["계좌번호"] = ""

    # 6. 첨부파일(사업자등록증 등) 업로드 시 추출값 보완
    if file_text.strip():
        # 사업자등록번호 (xxx-xx-xxxxx)
        biz_match = re.search(r"\d{3}\s*-\s*\d{2}\s*-\s*\d{5}", file_text)
        if biz_match:
            data["사업자번호"] = re.sub(r"\s+", "", biz_match.group(0))

        # 법인등록번호 (xxxxxx-xxxxxxx)
        corp_match = re.search(r"\d{6}\s*-\s*\d{7}", file_text)
        if corp_match:
            data["법인 번호"] = re.sub(r"\s+", "", corp_match.group(0))

        # 대표자명 보완
        if not data["대표자명"]:
            rep_file_match = re.search(
                r"(?:성\s*명|대\s*표\s*자)\s*[:\s]*([가-힣]{2,5})", file_text
            )
            if rep_file_match:
                data["대표자명"] = rep_file_match.group(1).strip()

        # 업태 / 종목 (증명서 표에서 "업태 도소매 종목 여행업"처럼 나란히 등장)
        ut = re.search(
            r"업\s*태[:\s]*(.+?)\s*종\s*[목류][:\s]*([^\n]+)", file_text
        )
        if ut:
            if not data["업태"]:
                data["업태"] = re.sub(r"\s+", " ", ut.group(1)).strip()
            if not data["업종"]:
                data["업종"] = re.sub(r"\s+", " ", ut.group(2)).strip()

        # 주소(소재지) — 라벨 종류 확대, '이메일 주소' 배제
        addr_match = re.search(
            r"(?:사업장\s*소재지|본점\s*소재지|소\s*재\s*지|도로명\s*주소)\s*[:\s]*([^\n]+)",
            file_text,
        )
        if addr_match:
            addr_val = re.sub(r"\s+", " ", addr_match.group(1)).strip()
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
