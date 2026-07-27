import io
import re
import pandas as pd
import streamlit as st

TARGET_COLUMNS = [
    "유형", "게시글 번호", "A코드", "대리점명", "대표자명", 
    "영업팀", "하나A", "핸드폰번호", "사업자번호", "관광사업자번호", 
    "법인 번호", "전화번호", "팩스번호", "이메일주소", "계좌번호", 
    "DTI", "업태", "업종"
]

def clean_phone_number(val):
    if pd.isna(val): return ""
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
    if pd.isna(val): return ""
    digits = re.sub(r"[^\d]", "", str(val))
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return str(val)

def validate_row(row):
    warnings = []
    biz = re.sub(r"[^\d]", "", str(row.get("사업자번호", "")))
    if biz and len(biz) != 10:
        warnings.append(f"사업자번호 자릿수 오류 ({biz})")
    email = str(row.get("이메일주소", ""))
    if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        warnings.append(f"이메일 형식 오류 ({email})")
    return warnings

st.set_page_config(page_title="데이터 가공 도구", layout="wide")
st.title("엑셀 복사용 데이터 가공 도구")

uploaded_file = st.file_uploader("파일 업로드 (Excel 또는 CSV)", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, dtype=str)
        else:
            df = pd.read_excel(uploaded_file, dtype=str)
    except Exception as e:
        st.error(f"파일 읽기 오류: {e}")
        st.stop()

    for col in TARGET_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[TARGET_COLUMNS]

    for phone_col in ["핸드폰번호", "전화번호", "팩스번호"]:
        df[phone_col] = df[phone_col].apply(clean_phone_number)
    df["사업자번호"] = df["사업자번호"].apply(clean_biz_no)

    st.subheader("크로스체크 결과")
    all_warnings = []
    for idx, row in df.iterrows():
        issues = validate_row(row)
        if issues:
            agency = row['대리점명'] if row['대리점명'] else f"{idx+1}번째 행"
            all_warnings.append(f"[{agency}] {', '.join(issues)}")
    
    if all_warnings:
        for warn in all_warnings:
            st.warning(warn)
    else:
        st.success("이상 항목 없음")

    tsv_data = df.to_csv(sep="\t", index=False)

    st.subheader("가공 데이터")
    st.dataframe(df)

    st.text_area("엑셀 복사용 텍스트 (전체 선택 후 복사하여 엑셀에 붙여넣기)", value=tsv_data, height=300)
