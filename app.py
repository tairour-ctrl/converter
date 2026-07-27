import io
import re
import pandas as pd
import streamlit as st
import pdfplumber

TARGET_COLUMNS = [
    "유형", "게시글 번호", "A코드", "대리점명", "대표자명", 
    "영업팀", "하나A", "핸드폰번호", "사업자번호", "관광사업자번호", 
    "법인 번호", "전화번호", "팩스번호", "이메일주소", "계좌번호", 
    "DTI", "업태", "업종", "사업자 소재지"
]

def clean_phone_number(val):
    if pd.isna(val) or not val: return ""
    digits = re.sub(r"[^\d]", "", str(val))
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    elif len(digits) == 10:
        if digits.startswith("02"):
            return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    elif len(digits) == 9:
        return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}"
    return str(val)

def clean_biz_no(val):
    if pd.isna(val) or not val: return ""
    digits = re.sub(r"[^\d]", "", str(val))
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return str(val)

def clean_corp_no(val):
    if pd.isna(val) or not val: return ""
    digits = re.sub(r"[^\d]", "", str(val))
    if len(digits) == 13:
        return f"{digits[:6]}-{digits[6:]}"
    return str(val)

def extract_acode(text):
    match = re.search(r"\b(PH\d{5}|A\d{4})\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else ""

def parse_text_data(text):
    data = {}
    data["A코드"] = extract_acode(text)
    
    email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    if email_match:
        data["이메일주소"] = email_match.group(0)

    phones = re.findall(r"\b01[016789]-?\d{3,4}-?\d{4}\b", text)
    if phones:
        data["핸드폰번호"] = clean_phone_number(phones[0])

    tel_matches = re.findall(r"\b0\d{1,2}-?\d{3,4}-?\d{4}\b", text)
    tel_filtered = [t for t in tel_matches if clean_phone_number(t) != data.get("핸드폰번호")]
    if tel_filtered:
        data["전화번호"] = clean_phone_number(tel_filtered[0])
    if len(tel_filtered) > 1:
        data["팩스번호"] = clean_phone_number(tel_filtered[1])

    post_num = re.search(r"(?:게시글\s*번호|글번호|게시글|번호)\s*[:=]?\s*(\d+)", text)
    if post_num:
        data["게시글 번호"] = post_num.group(1)

    type_match = re.search(r"(?:유형|구분)\s*[:=]?\s*([^\n,]+)", text)
    if type_match:
        data["유형"] = type_match.group(1).strip()

    agency_match = re.search(r"(?:대리점명|대리점|상호)\s*[:=]?\s*([^\n,]+)", text)
    if agency_match:
        data["대리점명"] = agency_match.group(1).strip()

    team_match = re.search(r"(?:영업팀|담당팀|영업)\s*[:=]?\s*([^\n,]+)", text)
    if team_match:
        data["영업팀"] = team_match.group(1).strip()

    hana_match = re.search(r"(?:하나A|하나a|하나코드)\s*[:=]?\s*([^\n,]+)", text)
    if hana_match:
        data["하나A"] = hana_match.group(1).strip()

    dti_match = re.search(r"(?:DTI|dti)\s*[:=]?\s*([^\n,]+)", text)
    if dti_match:
        data["DTI"] = dti_match.group(1).strip()

    return data

def parse_file_data(uploaded_files):
    data = {}
    combined_text = ""

    for file in uploaded_files:
        if file.name.endswith(".pdf"):
            try:
                with pdfplumber.open(file) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            combined_text += page_text + "\n"
            except Exception:
                pass
        elif file.name.endswith((".xlsx", ".xls")):
            try:
                df_temp = pd.read_excel(file, dtype=str)
                combined_text += df_temp.to_string() + "\n"
            except Exception:
                pass
        elif file.name.endswith(".csv"):
            try:
                df_temp = pd.read_csv(file, dtype=str)
                combined_text += df_temp.to_string() + "\n"
            except Exception:
                pass
        elif file.name.endswith(".txt"):
            try:
                combined_text += file.read().decode("utf-8") + "\n"
            except Exception:
                pass

    biz_match = re.search(r"\b\d{3}-?\d{2}-?\d{5}\b", combined_text)
    if biz_match:
        data["사업자번호"] = clean_biz_no(biz_match.group(0))

    corp_match = re.search(r"\b\d{6}-?\d{7}\b", combined_text)
    if corp_match:
        data["법인 번호"] = clean_corp_no(corp_match.group(0))

    tour_match = re.search(r"(?:관광사업자번호|관광사업등록번호|관광등록번호)\s*[:=]?\s*([^\n,]+)", combined_text)
    if tour_match:
        data["관광사업자번호"] = tour_match.group(1).strip()

    addr_match = re.search(r"(?:소재지|주소|사업장소재지)\s*[:=]?\s*([^\n]+)", combined_text)
    if addr_match:
        data["사업자 소재지"] = addr_match.group(1).strip()

    uptae_match = re.search(r"(?:업태)\s*[:=]?\s*([^\n\t,]+)", combined_text)
    if uptae_match:
        data["업태"] = uptae_match.group(1).strip()

    upjong_match = re.search(r"(?:업종|종목)\s*[:=]?\s*([^\n\t,]+)", combined_text)
    if upjong_match:
        data["업종"] = upjong_match.group(1).strip()

    account_match = re.search(r"(?:계좌번호|계좌|입금계좌)\s*[:=]?\s*([0-9-]{9,20})", combined_text)
    if account_match:
        data["계좌번호"] = account_match.group(1).strip()

    rep_match = re.search(r"(?:대표자명|대표자|대표)\s*[:=]?\s*([^\n,]+)", combined_text)
    if rep_match:
        data["대표자명"] = rep_match.group(1).strip()

    return data

def validate_row(row):
    warnings = []
    biz = re.sub(r"[^\d]", "", str(row.get("사업자번호", "")))
    if biz and len(biz) != 10:
        warnings.append(f"사업자번호 자릿수 오류 ({biz})")
    
    acode = str(row.get("A코드", ""))
    if acode and not re.match(r"^(PH\d{5}|A\d{4})$", acode, re.IGNORECASE):
        warnings.append(f"A코드 형식 오류 ({acode})")
        
    email = str(row.get("이메일주소", ""))
    if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        warnings.append(f"이메일 형식 오류 ({email})")
        
    return warnings

st.set_page_config(page_title="자동 추출 & 데이터 가공 도구", layout="wide")
st.title("텍스트 + 첨부파일 데이터 자동 추출 & 엑셀 가공 도구")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 텍스트 입력 (텍스트 기반 추출)")
    raw_text = st.text_area("텍스트를 붙여넣으세요 (유형, 게시글번호, A코드, 대리점명, 영업팀, 하나A, 핸드폰, 전화, 팩스, 이메일, DTI)", height=250)

with col2:
    st.subheader("2. 첨부파일 업로드 (파일 기반 추출)")
    uploaded_files = st.file_uploader("사업자등록증, 통장사본 등 첨부파일 (PDF, Excel, CSV, TXT)", type=["pdf", "xlsx", "xls", "csv", "txt"], accept_multiple_files=True)

if st.button("데이터 추출 및 통합 시작"):
    extracted_data = {col: "" for col in TARGET_COLUMNS}
    
    if raw_text:
        text_parsed = parse_text_data(raw_text)
        extracted_data.update(text_parsed)
        
    if uploaded_files:
        file_parsed = parse_file_data(uploaded_files)
        extracted_data.update({k: v for k, v in file_parsed.items() if v})

    df = pd.DataFrame([extracted_data])[TARGET_COLUMNS]

    st.subheader("크로스체크 및 검증 결과")
    warnings = validate_row(df.iloc[0])
    if warnings:
        for w in warnings:
            st.warning(w)
    else:
        st.success("데이터 이상 없음 (A코드 및 주요 항목 규격 정상)")

    tsv_data = df.to_csv(sep="\t", index=False)

    st.subheader("추출 및 가공 데이터 미리보기")
    st.dataframe(df)

    st.text_area("엑셀 복사용 결과 텍스트 (전체 선택 후 복사하여 엑셀에 붙여넣기)", value=tsv_data, height=150)
