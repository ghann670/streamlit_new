import streamlit as st
import pandas as pd
import plotly.express as px
import altair as alt
import matplotlib.pyplot as plt
from urllib.parse import parse_qs
import os, requests, io

# Page config
st.set_page_config(page_title="Usage Summary", page_icon="📊", layout="wide")

# 캐시 클리어 (디버깅용)
if st.button("🔄 Clear Cache & Refresh"):
    st.cache_data.clear()
    st.rerun()

USAGE_LOCAL = "df_usage.xlsx"
USAGE_URL = "https://raw.githubusercontent.com/ghann670/streamlit/main/df_usage.xlsx"

USERS_LOCAL = "df_users.xlsx"
USERS_URL = "https://raw.githubusercontent.com/ghann670/streamlit_new/main/df_users.xlsx"

USERS_DATE_LOCAL = "users.xlsx"
USERS_DATE_URL = "https://raw.githubusercontent.com/ghann670/streamlit_new/main/users.xlsx"

@st.cache_data(show_spinner=False)
def load_trial_dates_df() -> pd.DataFrame:
    """Load trial dates data from users.xlsx date sheet"""
    # Try local first
    if os.path.exists(USERS_DATE_LOCAL):
        try:
            return pd.read_excel(USERS_DATE_LOCAL, sheet_name='date')
        except Exception as e:
            st.warning(f"Failed to read local '{USERS_DATE_LOCAL}' date sheet: {e}. Falling back to remote…")
    # Fall back to remote
    try:
        r = requests.get(USERS_DATE_URL, timeout=30)
        r.raise_for_status()
        return pd.read_excel(io.BytesIO(r.content), sheet_name='date')
    except Exception as e:
        st.error("Failed to load trial dates data from both local file and remote URL.")
        st.stop()

@st.cache_data(show_spinner=False)
def load_users_df() -> pd.DataFrame:
    """Load users data from local file if available, else fall back to remote URL.
    Stops the app with an error message if both sources fail."""
    # Try local first
    if os.path.exists(USERS_LOCAL):
        try:
            return pd.read_excel(USERS_LOCAL)
        except Exception as e:
            st.warning(f"Failed to read local '{USERS_LOCAL}': {e}. Falling back to remote…")
    # Fall back to remote
    try:
        r = requests.get(USERS_URL, timeout=30)
        r.raise_for_status()
        return pd.read_excel(io.BytesIO(r.content))
    except Exception as e:
        st.error("Failed to load users data from both local file and remote URL. Please check the data source.")
        st.stop()

@st.cache_data(show_spinner=False)
def load_usage_df() -> pd.DataFrame:
    """Load usage data from local file if available, else fall back to remote URL.
    Stops the app with an error message if both sources fail."""
    # Try local first
    if os.path.exists(USAGE_LOCAL):
        try:
            return pd.read_excel(USAGE_LOCAL)
        except Exception as e:
            st.warning(f"Failed to read local '{USAGE_LOCAL}': {e}. Falling back to remote…")
    # Fall back to remote
    try:
        r = requests.get(USAGE_URL, timeout=30)
        r.raise_for_status()
        return pd.read_excel(io.BytesIO(r.content))
    except Exception as e:
        st.error("Failed to load usage data from both local file and remote URL. Please check the data source.")
        st.stop()


df_usage = load_usage_df()
df_users = load_users_df()
df_trial_dates = load_trial_dates_df()

# df_usage 전처리 (df_all 대신 직접 사용)
# normalize helper
_norm = lambda s: "".join(str(s).strip().lower().replace("_", " ").split())
colmap = {_norm(c): c for c in df_usage.columns}
get = lambda name: colmap.get(_norm(name))

# rename to expected columns if present
rename_map = {}
for src, dst in [
    ("User Email", "user_email"),
    ("User Name", "user_name"),
    ("Organization", "organization"),
    ("Created At", "created_at"),
    ("Function Mode", "function_mode"),
    ("Selected Model", "selected_model"),
    ("Sender", "sender"),
    ("Time To First Byte", "time_to_first_byte"),
    ("Status", "status"),
    ("Division", "division"),
    ("Trial Start Date", "trial_start_date"),
]:
    src_col = get(src)
    if src_col:
        rename_map[src_col] = dst

df_usage = df_usage.rename(columns=rename_map)

# datetime parsing for df_usage
if "created_at" in df_usage.columns:
    df_usage['created_at'] = pd.to_datetime(df_usage['created_at'], errors='coerce', utc=True).dt.tz_localize(None)
if "trial_start_date" in df_usage.columns:
    df_usage['trial_start_date'] = pd.to_datetime(df_usage['trial_start_date'], errors='coerce')

# preprocessing for df_usage
df_usage['day_bucket'] = df_usage['created_at'].dt.date if 'created_at' in df_usage.columns else pd.NaT
df_usage['agent_type'] = df_usage['function_mode'].astype(str).str.split(":").str[0] if 'function_mode' in df_usage.columns else "normal"

# 절감 시간 매핑
time_map = {"deep_research": 40, "pulse_check": 30}
df_usage["saved_minutes"] = df_usage["agent_type"].map(time_map).fillna(30)

# UI 설정
st.title("\U0001F680 Usage Summary Dashboard")

# 조직 리스트 추출 (df_usage 기준)
org_event_counts = (
    df_usage
    .groupby('organization')
    .size()
    .sort_values(ascending=False)
)
org_list_sorted = org_event_counts.index.tolist()

# URL에서 selected_org 파라미터 읽기
default_org = st.query_params.get("selected_org", None)

# 기본 선택 조직 설정
if default_org in org_list_sorted:
    default_index = org_list_sorted.index(default_org)
else:
    default_index = 0

# 조직 선택
selected_org = st.selectbox("Select Organization", org_list_sorted, index=default_index)

# 선택된 조직의 usage 데이터 필터링
df_usage_org = df_usage[df_usage['organization'] == selected_org]

# users.xlsx의 date 시트에서 정확한 trial_start_date 가져오기
org_trial_info = df_trial_dates[df_trial_dates['organization'] == selected_org]
if not org_trial_info.empty:
    trial_start_date = pd.to_datetime(org_trial_info['trial_start_date'].iloc[0])
else:
    # fallback: organization의 첫 이벤트 날짜 사용
    if not df_usage_org.empty and not df_usage_org['created_at'].isna().all():
        trial_start_date = df_usage_org['created_at'].min()
    else:
        trial_start_date = pd.Timestamp.now()
        
df_usage_org['trial_start_date'] = trial_start_date

# Metric 계산 - df_users.xlsx와 df_usage 기반으로 수정  
total_events = len(df_usage_org)  # All Events = 선택된 조직의 usage 데이터 전체 카운트

# df_users에서 선택된 organization의 total users 계산
if 'organization' in df_users.columns:
    df_users_org = df_users[df_users['organization'] == selected_org]
else:
    # organization 컬럼이 없으면 전체 사용자
    df_users_org = df_users

total_users = df_users_org['user_email'].nunique()  # 중복 제거

# df_users에서 status가 'active'인 사용자 계산 (중복 제거)
if 'status' in df_users_org.columns:
    active_users = df_users_org[df_users_org['status'] == 'active']['user_email'].nunique()
else:
    # status 컬럼이 없으면 모든 사용자를 active로 간주
    active_users = total_users

active_ratio = f"{active_users} / {total_users}"

# df_usage_active 정의 (여러 섹션에서 사용)
if 'user_email' in df_users_org.columns and 'status' in df_users_org.columns:
    active_user_emails = df_users_org[df_users_org['status'] == 'active']['user_email'].tolist()
    df_usage_active = df_usage_org[df_usage_org['user_email'].isin(active_user_emails)]
else:
    df_usage_active = df_usage_org  # fallback to all usage

# Top user 계산
if not df_usage_active['user_name'].dropna().empty:
    top_user = df_usage_active['user_name'].value_counts().idxmax()
    top_user_count = df_usage_active['user_name'].value_counts().max()
    top_user_display = f"{top_user} ({top_user_count} times)"
else:
    top_user_display = "N/A"

# 평균 이벤트
avg_events = round(total_events / active_users, 1) if active_users > 0 else 0

# 절감 시간 (주차 계산 대신 전체 기간 사용)
if not df_usage_active.empty and active_users > 0:
    # 전체 사용 기간을 주 단위로 계산
    date_range = (df_usage_active['created_at'].max() - df_usage_active['created_at'].min()).days
    used_weeks = max(1, date_range // 7)  # 최소 1주
    total_saved_minutes = df_usage_active["saved_minutes"].sum()
    saved_minutes_per_user_per_week = round(total_saved_minutes / used_weeks / active_users, 1)
    saved_display = f"{saved_minutes_per_user_per_week} min"
else:
    saved_display = "—"

# ✅ Invited & No-Usage Users 추출 - df_users.xlsx 기반으로 수정 (중복 제거)
if 'status' in df_users_org.columns:
    invited_emails = df_users_org[df_users_org['status'] == 'invited_not_joined']['user_email'].dropna().unique() if 'user_email' in df_users_org.columns else []
    # joined but no usage = status가 null/NaN인 사용자들
    joined_no_usage_emails = df_users_org[df_users_org['status'].isna()]['user_email'].dropna().unique() if 'user_email' in df_users_org.columns else []
else:
    # status 컬럼이 없으면 빈 배열
    invited_emails = []
    joined_no_usage_emails = []

invited_display = ", ".join(invited_emails) if len(invited_emails) > 0 else "—"
joined_display = ", ".join(joined_no_usage_emails) if len(joined_no_usage_emails) > 0 else "—"

# Layout – Metrics
col1, col2, col3 = st.columns(3)
col1.metric("All Events", total_events)
col2.metric("Active / Total Users", active_ratio)
col3.metric("Top User", top_user_display)

col4, col5, col6 = st.columns(3)
# earnings, briefings 정보는 df_users에서 가져오기 (중복 제거)
earnings_users = df_users_org[df_users_org['earnings'] == 'onboarded']['user_email'].nunique() if 'earnings' in df_users_org.columns else 0
briefing_users = df_users_org[df_users_org['briefing'] == 'onboarded']['user_email'].nunique() if 'briefing' in df_users_org.columns else 0
col4.metric("Earnings/Briefing Users", f"{earnings_users}/{briefing_users}")
col5.metric("Avg. Events per Active User", avg_events)
col6.metric("Avg. Time Saved / User / Week", saved_display)

# User Status 섹션
st.markdown("### 👥 User Status")

# 2x2 그리드 생성
status_col1, status_col2 = st.columns(2)

with status_col1:
    # 왼쪽 열
    st.markdown("**Invited but Not Joined**")
    st.markdown(
        f"""
        <div style='
            max-height: 60px;
            overflow-y: auto;
            font-size: 13px;
            border: 1px solid #ccc;
            padding: 6px;
            border-radius: 5px;
            background-color: #fffaf5;
            margin-bottom: 15px;
        '>
            {invited_display}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("**Joined but No Usage**")
    st.markdown(
        f"""
        <div style='
            max-height: 60px;
            overflow-y: auto;
            font-size: 13px;
            border: 1px solid #ccc;
            padding: 6px;
            border-radius: 5px;
            background-color: #f5faff;
        '>
            {joined_display}
        </div>
        """,
        unsafe_allow_html=True
    )

with status_col2:
    # Normal만 사용한 유저 찾기
    all_users = df_usage_org['user_name'].unique()
    normal_only_users = []
    for user in all_users:
        user_types = df_usage_org[df_usage_org['user_name'] == user]['agent_type'].unique()
        if len(user_types) == 1 and user_types[0] == 'normal':
            normal_only_users.append(user)
    normal_only_users.sort()
    normal_only_display = ", ".join(normal_only_users) if normal_only_users else "—"

    # Recent 2 Weeks Active Users 찾기 (최근 2주간 활성 사용자)
    if not df_usage_active.empty and 'created_at' in df_usage_active.columns:
        # 최근 2주간 활성 사용자 찾기
        recent_date = df_usage_active['created_at'].max()
        if pd.notna(recent_date):
            two_weeks_ago = recent_date - pd.Timedelta(days=14)
            recent_users = df_usage_active[df_usage_active['created_at'] >= two_weeks_ago]['user_name'].dropna().unique()
            # 안전한 정렬을 위해 문자열 변환 후 빈 값 제거
            recent_users_clean = [str(user) for user in recent_users if pd.notna(user) and str(user).strip()]
            consistent_display = ", ".join(sorted(recent_users_clean)) if len(recent_users_clean) > 0 else "—"
        else:
            consistent_display = "—"
    else:
        consistent_display = "—"

    # 오른쪽 열
    st.markdown("**Recent 2 Weeks Active Users**")
    st.markdown(
        f"""
        <div style='
            max-height: 60px;
            overflow-y: auto;
            font-size: 13px;
            border: 1px solid #ccc;
            padding: 6px;
            border-radius: 5px;
            background-color: #f5fff5;
            margin-bottom: 15px;
        '>
            {consistent_display}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("**Normal Function Only Users**")
    st.markdown(
        f"""
        <div style='
            max-height: 60px;
            overflow-y: auto;
            font-size: 13px;
            border: 1px solid #ccc;
            padding: 6px;
            border-radius: 5px;
            background-color: #fff5ff;
        '>
            {normal_only_display}
        </div>
        """,
        unsafe_allow_html=True
    )



# Total usage 시계열 차트
st.markdown("---")
st.subheader("📅 Total Usage Over Time (All Functions)")

# 1️⃣ 날짜별 전체 사용량 집계
end_date = pd.Timestamp.now()
default_start = pd.Timestamp('2025-01-01')

# 조직별 trial_start_date 확인
df_active_org = df_usage_active.copy()

# 2024년 trial_start_date를 가진 조직은 2025-01-01부터 시작하도록 조정
df_active_org.loc[df_active_org['trial_start_date'].dt.year == 2024, 'trial_start_date'] = default_start

# 각 조직별로 데이터 처리
org_data_list = []
for org in df_active_org['organization'].unique():
    org_df = df_active_org[df_active_org['organization'] == org]
    
    try:
        # trial_start_date 처리
        org_start = org_df['trial_start_date'].iloc[0]
        
        # end_date 처리 (현재 시간으로부터)
        end_date = pd.Timestamp.now()
        
        # org_start가 유효한지 확인하고 처리
        if pd.isna(org_start) or not isinstance(org_start, pd.Timestamp):
            # created_at에서 최소값 찾기
            if not org_df['created_at'].empty:
                org_start = pd.to_datetime(org_df['created_at'].min())
            else:
                # 데이터가 없는 경우 스킵
                continue
        
        # 날짜가 유효한지 최종 확인
        if pd.isna(org_start) or pd.isna(end_date):
            print(f"Invalid dates for org {org}: start={org_start}, end={end_date}")
            continue
            
        # 시작일이 종료일보다 늦은 경우 처리
        if org_start > end_date:
            org_start = end_date
        
        # 해당 조직의 날짜 범위 생성
        org_dates = pd.date_range(
            start=org_start.normalize(),  # 시간 정보 제거
            end=end_date.normalize(),     # 시간 정보 제거
            freq='D'
        )
        
        # 데이터프레임 생성 및 처리
        org_date_df = pd.DataFrame({'created_at': org_dates})
        
        # 해당 조직의 실제 데이터 집계
        org_counts = org_df.groupby(org_df["created_at"].dt.date).size().reset_index(name="count")
        org_counts["created_at"] = pd.to_datetime(org_counts["created_at"])
        
        # 데이터 병합
        org_daily = pd.merge(org_date_df, org_counts, on='created_at', how='left')
        org_data_list.append(org_daily)
        
    except Exception as e:
        print(f"Error processing org {org}: {str(e)}")
        continue

# 모든 조직의 데이터 합치기
df_total_daily = pd.concat(org_data_list)
df_total_daily = df_total_daily.groupby('created_at')['count'].sum().reset_index()
df_total_daily['count'] = df_total_daily['count'].fillna(0)

# ✅ 2️⃣ 날짜 라벨 생성 (예: 7/11)
df_total_daily["date_label"] = df_total_daily["created_at"].dt.strftime("%-m/%d")  # macOS/Linux
# 윈도우는 "%#m/%d"

# ✅ Plotly 시계열 차트 (y축 상단 여유 포함)
fig1 = px.line(
    df_total_daily,
    x="created_at",  # date_label 대신 created_at 사용
    y="count",
    markers=True,
    labels={"created_at": "Date", "count": "Total Event Count"},
)

# ✅ 차트 레이아웃 설정
fig1.update_layout(
    height=300,
    width=900,
    xaxis=dict(
        rangeslider=dict(visible=True),  # 하단에 슬라이더 추가
        type="date",
        tickformat="%Y-%m-%d",
                    range=[df_total_daily['created_at'].min(), df_total_daily['created_at'].max()]  # x축 범위 설정
    ),
    margin=dict(l=50, r=50, t=30, b=50)  # 여백 조정
)

# ✅ y축 범위 자동보다 조금 더 크게 설정
max_count = df_total_daily["count"].max()
fig1.update_yaxes(range=[0, max_count + 10])

st.plotly_chart(fig1, use_container_width=True)




# ✅ New Section: 유저별 라인차트 추가
st.markdown("### 👥 Users' Daily Usage (2025 Data Only)")

# 유저별 일별 사용량 집계 (각 유저의 첫 사용일부터 현재까지)
# 실제 사용량 데이터 집계 (2025년 데이터만)
df_2025 = df_usage_active[df_usage_active['created_at'].dt.year == 2025]

# 각 유저의 첫 사용일 찾기 (2025년 기준)
user_first_dates = df_2025.groupby('user_name')['created_at'].min().reset_index()
user_first_dates['created_at'] = user_first_dates['created_at'].dt.date
user_counts = df_2025.groupby(
    [df_2025["created_at"].dt.date, "user_name"]
).size().reset_index(name="count")

# 유저별 total usage 수 기준 정렬
user_total_counts = user_counts.groupby("user_name")["count"].sum()
sorted_users = user_total_counts.sort_values(ascending=False).index.tolist()
default_users = sorted_users[:3]  # 상위 3명 기본 선택

# 세션 상태에 선택 유저 목록 저장
if "selected_users" not in st.session_state:
    st.session_state.selected_users = default_users

# 전체 선택 / 해제 버튼
col1, col2 = st.columns([1, 1])
with col1:
    if st.button("✅ 전체 선택"):
        st.session_state.selected_users = sorted_users
with col2:
    if st.button("❌ 전체 해제"):
        st.session_state.selected_users = []

# 멀티셀렉트 (세션 상태로 동기화, 유효성 보정)
valid_default_users = [user for user in st.session_state.selected_users if user in sorted_users]

selected_users = st.multiselect(
    "Select users to display",
    options=sorted_users,
    default=valid_default_users,
    key="selected_users"
)

# 2025년 데이터의 최대 날짜 사용
actual_end_date = df_2025['created_at'].max().date() if not df_2025.empty else pd.Timestamp.now().date()

# 선택된 유저들의 데이터만 처리
df_user_daily_list = []
for user in selected_users:
    user_start = user_first_dates[user_first_dates['user_name'] == user]['created_at'].iloc[0]
    user_dates = pd.date_range(start=user_start, end=actual_end_date, freq='D')
    
    # 해당 유저의 날짜별 데이터 생성
    user_df = pd.DataFrame({'created_at': user_dates})
    user_df['user'] = user
    
    # 실제 데이터와 병합
    user_counts_filtered = user_counts[user_counts['user_name'] == user].copy()
    user_counts_filtered['created_at'] = pd.to_datetime(user_counts_filtered['created_at'])
    
    user_df = pd.merge(
        user_df,
        user_counts_filtered[['created_at', 'count']],
        on='created_at',
        how='left'
    )
    df_user_daily_list.append(user_df)

# 모든 유저 데이터 합치기
if df_user_daily_list:
    df_user_filtered = pd.concat(df_user_daily_list, ignore_index=True)
    df_user_filtered['count'] = df_user_filtered['count'].fillna(0)
    df_user_filtered["date_label"] = df_user_filtered["created_at"].dt.strftime("%-m/%d")
else:
    df_user_filtered = pd.DataFrame(columns=['created_at', 'user', 'count', 'date_label'])

# ✅ 라인차트 시각화
if df_user_filtered.empty:
    st.info("No data for selected users.")
else:
    chart_users = alt.Chart(df_user_filtered).mark_line(point=True).encode(
        x=alt.X(
            "created_at:T",
            title="Date",
            axis=alt.Axis(
                labelAngle=0,
                format="%m/%d",
                tickCount={"interval": "day", "step": 1},  # 하루 간격으로 눈금 표시
                grid=True
            )
        ),
        y=alt.Y("count:Q", title="Event Count"),
        color=alt.Color("user:N", title="User", sort=sorted_users),
        tooltip=[
            alt.Tooltip("created_at:T", title="Date", format="%Y-%m-%d"),
            alt.Tooltip("user:N", title="User"),
            alt.Tooltip("count:Q", title="Count")
        ]
    ).properties(width=900, height=300)
    
    st.altair_chart(chart_users, use_container_width=True)

    # 테이블 추가
    st.markdown("#### Daily Usage Table")
    
    # 피벗 테이블 생성
    df_user_filtered['date_col'] = df_user_filtered['created_at'].dt.strftime("%m/%d")
    table_data = df_user_filtered.pivot_table(
        index='user',
        columns='date_col',
        values='count',
        fill_value=0
    )
    
    # 날짜 컬럼을 시간순으로 정렬
    date_columns = [col for col in table_data.columns if col != 'Total']
    # 실제 데이터에서 해당 날짜의 연도를 찾아서 정렬
    def get_actual_date_for_sorting(date_str):
        matching_dates = df_user_filtered[df_user_filtered['created_at'].dt.strftime("%m/%d") == date_str]['created_at']
        if not matching_dates.empty:
            return matching_dates.min()
        else:
            return pd.to_datetime(f"2025/{date_str}")  # 2025년 기본값으로 변경
    
    sorted_date_columns = sorted(date_columns, key=get_actual_date_for_sorting)
    
    # Total 컬럼 추가
    table_data['Total'] = table_data.sum(axis=1)
    
    # Total 기준으로 정렬
    table_data = table_data.sort_values('Total', ascending=False)
    
    # Total을 맨 앞으로, 그 다음 날짜를 시간순으로 배치
    cols = ['Total'] + sorted_date_columns
    table_data = table_data[cols]
    
    # Total 행 추가
    table_data.loc['Total'] = table_data.sum(numeric_only=True)
    
    # 0을 '-'로 대체하기 전에 정수로 변환
    table_data = table_data.apply(lambda x: x.astype(float).astype(int) if pd.api.types.is_numeric_dtype(x) else x)
    table_data = table_data.replace(0, '-')
    
    st.dataframe(table_data.astype(object), use_container_width=True)




# 함수 및 주간 시계열
st.markdown("---")

# Trial Start Date 계산
try:
    trial_start = pd.to_datetime(df_usage_org['trial_start_date'].iloc[0]).strftime('%Y-%m-%d')
except (IndexError, pd.errors.OutOfBoundsDatetime):
    trial_start = pd.Timestamp.now().strftime('%Y-%m-%d')

# View Mode 선택
view_mode = st.radio(
    "Select View Mode",
    ["Recent 4 Weeks", f"Trial Period (Trial Start Date: {trial_start})"],
    horizontal=True,
    key="function_trends_view_mode"
)

st.subheader("📈 Weekly Function Usage Trends")

# 주차 범위 설정 (Recent 4 Weeks 모드에서만 사용)
if view_mode == "Recent 4 Weeks":
    # 기준 날짜: 오늘 날짜 정오 기준
    now = pd.Timestamp.now().normalize() + pd.Timedelta(hours=12)
    
    # 각 주차 범위 설정
    week_ranges = {
        'week4': (now - pd.Timedelta(days=6), now),
        'week3': (now - pd.Timedelta(days=13), now - pd.Timedelta(days=7)),
        'week2': (now - pd.Timedelta(days=20), now - pd.Timedelta(days=14)),
        'week1': (now - pd.Timedelta(days=27), now - pd.Timedelta(days=21)),
    }
    
    # 주차 버킷 할당 함수
    def assign_week_bucket(date):
        if pd.isna(date):
            return None
        # date는 이미 timezone-naive 상태
        for week, (start, end) in week_ranges.items():
            if start <= date <= end:
                return week
        return None
    
    # 이 섹션에서만 week_bucket 할당
    df_usage_org['week_bucket'] = df_usage_org['created_at'].apply(assign_week_bucket)

if view_mode == f"Trial Period (Trial Start Date: {trial_start})":
    # trial_start_date 기준으로 주차 계산
    df_usage_org['week_from_trial'] = ((df_usage_org['created_at'] - df_usage_org['trial_start_date'])
                                .dt.days // 7 + 1)
    
    # trial_start_date와 같은 날짜(0)도 1주차로 처리
    df_usage_org.loc[df_usage_org['week_from_trial'] <= 1, 'week_from_trial'] = 1
    
    # week 포맷팅 (소수점 제거)
    df_usage_org['week_from_trial'] = df_usage_org['week_from_trial'].fillna(1)  # nan을 1로 처리
    df_usage_org['week_from_trial'] = df_usage_org['week_from_trial'].map(lambda x: f'Trial Week {int(x)}')
    
    df_chart = df_usage_org.groupby(['week_from_trial', 'agent_type']).size().reset_index(name='count')
    
    # 누락된 week_from_trial, agent_type 조합 채워넣기
    all_weeks = sorted(df_usage_org['week_from_trial'].unique())
    all_agents = df_chart['agent_type'].unique()
    all_combinations = pd.MultiIndex.from_product([all_weeks, all_agents], names=['week_from_trial', 'agent_type']).to_frame(index=False)
    df_chart = pd.merge(all_combinations, df_chart, on=['week_from_trial', 'agent_type'], how='left')
    df_chart['count'] = df_chart['count'].fillna(0).astype(int)
else:
    df_chart = df_usage_org.groupby(['week_bucket', 'agent_type']).size().reset_index(name='count')

    # 누락된 week_bucket, agent_type 조합 채워넣기
    all_weeks = list(week_ranges.keys())
    all_agents = df_chart['agent_type'].unique()
    all_combinations = pd.MultiIndex.from_product([all_weeks, all_agents], names=['week_bucket', 'agent_type']).to_frame(index=False)
    df_chart = pd.merge(all_combinations, df_chart, on=['week_bucket', 'agent_type'], how='left')
    df_chart['count'] = df_chart['count'].fillna(0).astype(int)

# Pivot Table - 모드에 따라 컬럼 이름 변경
if view_mode == "Recent 4 Weeks":
    df_week_table = df_chart.pivot_table(
        index='agent_type',
        columns='week_bucket',
        values='count',
        fill_value=0,
        aggfunc='sum'
    )
else:
    df_week_table = df_chart.pivot_table(
        index='agent_type',
        columns='week_from_trial',
        values='count',
        fill_value=0,
        aggfunc='sum'
    )

df_week_table['Total'] = df_week_table.sum(axis=1)
df_week_table = df_week_table.sort_values('Total', ascending=False)

# Trial Week 컬럼들을 숫자 순서로 정렬
if view_mode != "Recent 4 Weeks":
    # Trial Week 컬럼들만 추출하고 숫자로 정렬
    trial_week_cols = [col for col in df_week_table.columns if col != 'Total' and 'Trial Week' in str(col)]
    # Trial Week 숫자 추출해서 정렬
    trial_week_cols.sort(key=lambda x: int(x.split()[-1]))
    df_week_table = df_week_table[['Total'] + trial_week_cols]
else:
    df_week_table = df_week_table[['Total'] + [col for col in df_week_table.columns if col != 'Total']]

df_week_table.loc['Total'] = df_week_table.sum(numeric_only=True)

# 0을 '-'로 대체
df_week_table = df_week_table.replace(0, '-')

# 차트 정렬 순서 설정
sorted_agent_order = df_week_table.drop("Total").index.tolist()

if view_mode == "Recent 4 Weeks":
    df_chart['agent_type'] = pd.Categorical(df_chart['agent_type'], categories=sorted_agent_order, ordered=True)
    df_chart = df_chart.sort_values('agent_type')
    
    left, right = st.columns([6, 6])
    with left:
        chart_week = alt.Chart(df_chart).mark_line(point=True).encode(
            x=alt.X('week_bucket:N', title='Week', axis=alt.Axis(labelAngle=0)),
            y=alt.Y('count:Q', title='Event Count'),
            color=alt.Color('agent_type:N', title='Function', sort=sorted_agent_order),
            tooltip=['agent_type', 'count']
        ).properties(width=600, height=300)
        
        st.altair_chart(chart_week, use_container_width=True)
else:
    df_chart['agent_type'] = pd.Categorical(df_chart['agent_type'], categories=sorted_agent_order, ordered=True)
    df_chart = df_chart.sort_values(['week_from_trial', 'agent_type'])
    
    left, right = st.columns([6, 6])
    with left:
        chart_week = alt.Chart(df_chart).mark_line(point=True).encode(
            x=alt.X('week_from_trial:N', title='Trial Week', axis=alt.Axis(labelAngle=0)),
            y=alt.Y('count:Q', title='Event Count'),
            color=alt.Color('agent_type:N', title='Function', sort=sorted_agent_order),
            tooltip=['agent_type', 'count']
        ).properties(width=600, height=300)
        
        st.altair_chart(chart_week, use_container_width=True)

with right:
    st.dataframe(df_week_table.astype(object), use_container_width=True)


# 📊 Daily usage 시계열
st.subheader("📊 Daily Function Usage for a Selected Week")



# 📅 주차 선택 - view mode에 따라 다르게
if view_mode == "Recent 4 Weeks":
    # week_bucket이 없으면 생성
    if 'week_bucket' not in df_usage_org.columns:
        # 기준 날짜: 오늘 날짜 정오 기준
        now = pd.Timestamp.now().normalize() + pd.Timedelta(hours=12)
        
        # 각 주차 범위 설정
        week_ranges = {
            'week4': (now - pd.Timedelta(days=6), now),
            'week3': (now - pd.Timedelta(days=13), now - pd.Timedelta(days=7)),
            'week2': (now - pd.Timedelta(days=20), now - pd.Timedelta(days=14)),
            'week1': (now - pd.Timedelta(days=27), now - pd.Timedelta(days=21)),
        }
        
        # 주차 버킷 할당 함수
        def assign_week_bucket(date):
            if pd.isna(date):
                return None
            for week, (start, end) in week_ranges.items():
                if start <= date <= end:
                    return week
            return None
        
        df_usage_org['week_bucket'] = df_usage_org['created_at'].apply(assign_week_bucket)
    
    week_options = sorted(df_usage_org['week_bucket'].dropna().unique(), reverse=True)
    selected_week = st.selectbox("Select Week", week_options, key="daily_select_week")
    
    # 선택된 주차의 날짜 범위 계산
    week_start, week_end = week_ranges[selected_week]
    week_dates = pd.date_range(week_start, week_end).date
else:
    # Trial Period Mode
    # 모든 가능한 Trial Week 생성 (1주차부터 현재까지)
    max_week = ((pd.Timestamp.now() - df_usage_org['trial_start_date'].min()).days // 7) + 1
    week_options = [f'Trial Week {i}' for i in range(max_week, 0, -1)]
    selected_week = st.selectbox("Select Week", week_options, key="daily_select_week")
    
    # 선택된 Trial Week의 숫자 추출
    week_num = int(selected_week.split()[-1])
    
    # 해당 주차의 날짜 범위 계산
    trial_start = pd.to_datetime(df_usage_org['trial_start_date'].iloc[0])
    week_start = trial_start + pd.Timedelta(days=(week_num-1)*7)
    week_end = week_start + pd.Timedelta(days=6)
    week_dates = pd.date_range(week_start, week_end).date

# 📆 선택된 주간 데이터 필터링 (df_usage_active 사용)
df_week = df_usage_active[df_usage_active['created_at'].dt.date.isin(week_dates)]

# 📊 일별-기능별 집계
agent_types = df_usage_active['agent_type'].unique()  # 전체 기능 목록 사용

# 선택된 주의 모든 날짜와 기능 조합 생성
date_range = pd.date_range(start=min(week_dates), end=max(week_dates), freq='D')
all_combinations = pd.MultiIndex.from_product(
    [date_range, agent_types],
    names=['created_at', 'agent_type']
).to_frame(index=False)

# 실제 데이터 집계
df_day = df_week.groupby([df_week['created_at'].dt.date, 'agent_type']).size().reset_index(name='count')
df_day['created_at'] = pd.to_datetime(df_day['created_at'])

# 모든 날짜-기능 조합에 대해 데이터 병합 (없는 날짜는 0으로 표시)
df_day = pd.merge(all_combinations, df_day, on=['created_at', 'agent_type'], how='left')
df_day['count'] = df_day['count'].fillna(0).astype(int)

# 📊 기능별 정렬 기준 계산 (많이 쓴 순서 → 아래층부터 쌓임)
agent_order_by_volume = (
    df_day.groupby('agent_type')['count']
    .sum()
    .sort_values(ascending=False)
    .index.tolist()
)
agent_order_for_stack = agent_order_by_volume  # 많이 쓴 순서대로 스택

# 🔁 정렬 순서 적용
df_day['agent_type'] = pd.Categorical(
    df_day['agent_type'],
    categories=agent_order_for_stack,
    ordered=True
)
df_day = df_day.sort_values(['created_at', 'agent_type'], ascending=[True, True])

# 📈 Plotly 차트 + 📋 테이블
left2, right2 = st.columns([6, 6])
with left2:
    # 📊 Plotly stacked bar chart
    fig_day = px.bar(
        df_day,
        x="created_at",
        y="count",
        color="agent_type",
        category_orders={"agent_type": agent_order_for_stack},
        color_discrete_sequence=px.colors.qualitative.Set1,
        labels={"created_at": "Date", "count": "Event Count", "agent_type": "Function"},
    )
    
    # 차트 레이아웃 설정
    fig_day.update_layout(
        barmode="stack",
        width=600,
        height=300,
        xaxis_title="Date",
        yaxis_title="Event Count",
        legend_title="Function",
        showlegend=True if df_day['count'].sum() > 0 else False  # 데이터가 있을 때만 범례 표시
    )
    
    # x축 날짜 포맷 설정
    fig_day.update_xaxes(
        tickformat="%m-%d",
        type='date',
        dtick="D1",  # 하루 간격으로 눈금 표시
        range=[min(week_dates), max(week_dates)]  # 선택된 주의 전체 날짜 범위 표시
    )
    
    st.plotly_chart(fig_day, use_container_width=True)

with right2:
    # 📊 집계 테이블 준비
    df_day_table = df_day.pivot_table(
        index='agent_type',
        columns='created_at',
        values='count',
        fill_value=0,
        aggfunc='sum'
    )
    
    # 컬럼 이름을 mm-dd 형식으로 변경
    df_day_table.columns = pd.to_datetime(df_day_table.columns).strftime('%m-%d')
    
    # 날짜 컬럼을 시간순으로 정렬 (실제 데이터의 연도 사용)
    date_columns = [col for col in df_day_table.columns if col != 'Total']
    # 실제 데이터에서 해당 날짜의 연도를 찾아서 정렬
    def get_actual_date_for_day_sorting(date_str):
        # mm-dd 형식의 날짜 문자열에 대해 실제 데이터에서 해당하는 전체 날짜 찾기
        matching_dates = df_day[df_day['created_at'].dt.strftime("%m-%d") == date_str]['created_at']
        if not matching_dates.empty:
            return matching_dates.min()  # 가장 이른 날짜 사용
        else:
            return pd.to_datetime(f"2024-{date_str}")  # 기본값
    
    sorted_date_columns = sorted(date_columns, key=get_actual_date_for_day_sorting)
    
    df_day_table['Total'] = df_day_table.sum(axis=1)
    df_day_table = df_day_table.sort_values('Total', ascending=False)
    df_day_table = df_day_table[['Total'] + sorted_date_columns]
    df_day_table.loc['Total'] = df_day_table.sum(numeric_only=True)

    # 0을 '-'로 대체
    df_day_table = df_day_table.replace(0, '-')

    st.dataframe(df_day_table.astype(object), use_container_width=True)


# 👥 Function Usage by User
st.subheader("👥 Function Usage by User")

# 전체 유저 리스트 (모든 주차의 유저를 포함하도록)
all_users = sorted(df_usage_org['user_name'].dropna().unique())

# 세션 상태에 선택된 유저 저장
if "selected_user_for_function" not in st.session_state:
    st.session_state.selected_user_for_function = "All Users"

# 유저 필터 추가 (세션 상태 사용)
selected_user = st.selectbox(
    "Select User (Optional)", 
    ["All Users"] + all_users,
    key="selected_user_for_function"
)

# 📅 주차 선택 - view mode에 따라 다르게
if view_mode == "Recent 4 Weeks":
    week_options = sorted(df_usage_org['week_bucket'].dropna().unique(), reverse=True)
    selected_week = st.selectbox("Select Week", week_options, key="user_week_select")
    
    # 선택된 주차의 날짜 범위 계산
    week_start, week_end = week_ranges[selected_week]
    week_dates = pd.date_range(week_start, week_end).date
else:
    # Trial Period Mode
    # Trial Week 숫자 추출해서 내림차순 정렬
    week_options = sorted(df_usage_org['week_from_trial'].unique(), 
                         key=lambda x: int(x.split()[-1]),
                         reverse=True)
    selected_week = st.selectbox("Select Week", week_options, key="user_week_select")
    
    # 선택된 Trial Week의 숫자 추출
    week_num = int(selected_week.split()[-1])
    
    # 해당 주차의 날짜 범위 계산
    trial_start = pd.to_datetime(df_usage_org['trial_start_date'].iloc[0])
    week_start = trial_start + pd.Timedelta(days=(week_num-1)*7)
    week_end = week_start + pd.Timedelta(days=6)
    week_dates = pd.date_range(week_start, week_end).date

# 선택된 주간 데이터 필터링
df_user_week = df_usage_org[df_usage_org['created_at'].dt.date.isin(week_dates)]

# 기본 집계 데이터 준비 (전체 유저)
df_user_stack_full = df_user_week.groupby(['user_name', 'agent_type']).size().reset_index(name='count')

# 👉 기능 정렬 기준 정의 (많이 쓴 순)
sorted_func_order = (
    df_user_stack_full.groupby('agent_type')['count']
    .sum().sort_values(ascending=False).index.tolist()
)

# ✅ 왼쪽: 차트용 - top 10 유저만 필터링
top_users = (
    df_user_stack_full.groupby('user_name')['count']
    .sum().nlargest(10).index.tolist()
)
df_user_stack_chart = df_user_stack_full[df_user_stack_full['user_name'].isin(top_users)].copy()
df_user_stack_chart['agent_type'] = pd.Categorical(
    df_user_stack_chart['agent_type'],
    categories=sorted_func_order,
    ordered=True
)
df_user_stack_chart = df_user_stack_chart.sort_values(['user_name', 'agent_type'])

# 📊 시각화
left, right = st.columns([7, 5])
with left:
    fig = px.bar(
        df_user_stack_chart,
        x="user_name",
        y="count",
        color="agent_type",
        category_orders={
            "agent_type": sorted_func_order,
            "user_name": top_users
        },
        color_discrete_sequence=px.colors.qualitative.Set1,
        labels={"user_name": "User", "count": "Usage Count", "agent_type": "Function"},
    )
    fig.update_layout(
        barmode="stack",
        xaxis_title="User",
        yaxis_title="Usage Count",
        legend_title="Function",
        height=350,
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    if selected_user == "All Users":
        # 전체 유저 요약 테이블
        df_user_table = df_user_stack_full.pivot_table(
            index='agent_type',  # agent_type을 행으로
            columns='user_name',  # user를 열로
            values='count',
            aggfunc='sum',
            fill_value=0
        )
        
        # Total 컬럼 추가 및 정렬
        df_user_table['Total'] = df_user_table.sum(axis=1)
        df_user_table = df_user_table.sort_values('Total', ascending=False)
        df_user_table = df_user_table[['Total'] + [col for col in df_user_table.columns if col != 'Total']]
        
        # Total 행 추가
        df_user_table.loc['Total'] = df_user_table.sum(numeric_only=True)
        
    else:
        # 선택된 유저의 일별 상세 데이터
        df_user_detail = df_user_week[df_user_week['user_name'] == selected_user]
        
        # 모든 날짜와 agent_type 조합 생성
        all_dates = pd.date_range(week_start, week_end).strftime('%m/%d')
        all_agent_types = sorted_func_order
        all_combinations = pd.MultiIndex.from_product(
            [all_agent_types, all_dates],
            names=['agent_type', 'date']
        ).to_frame(index=False)
        
        # 실제 데이터 집계
        df_user_detail['date'] = df_user_detail['created_at'].dt.strftime('%m/%d')
        df_user_counts = df_user_detail.groupby(['agent_type', 'date']).size().reset_index(name='count')
        
        # 모든 조합과 실제 데이터 병합
        df_user_counts = pd.merge(
            all_combinations,
            df_user_counts,
            on=['agent_type', 'date'],
            how='left'
        ).fillna(0)
        
        # 피벗 테이블 생성
        df_user_table = df_user_counts.pivot_table(
            index='agent_type',
            columns='date',
            values='count',
            fill_value=0
        )
        
        # 날짜 컬럼을 시간순으로 정렬 (실제 데이터의 연도 사용)
        date_columns = [col for col in df_user_table.columns if col != 'Total']
        # 실제 데이터에서 해당 날짜의 연도를 찾아서 정렬
        def get_actual_date_for_user_sorting(date_str):
            # mm/dd 형식의 날짜 문자열에 대해 실제 데이터에서 해당하는 전체 날짜 찾기
            matching_dates = df_user_detail[df_user_detail['created_at'].dt.strftime("%m/%d") == date_str]['created_at']
            if not matching_dates.empty:
                return matching_dates.min()  # 가장 이른 날짜 사용
            else:
                return pd.to_datetime(f"2024/{date_str}")  # 기본값
        
        sorted_date_columns = sorted(date_columns, key=get_actual_date_for_user_sorting)
        
        # Total 컬럼 추가 및 정렬
        df_user_table['Total'] = df_user_table.sum(axis=1)
        df_user_table = df_user_table.sort_values('Total', ascending=False)
        df_user_table = df_user_table[['Total'] + sorted_date_columns]
        
        # Total 행 추가
        df_user_table.loc['Total'] = df_user_table.sum(numeric_only=True)
    
    st.dataframe(df_user_table.astype(object), use_container_width=True)


# 📊 Response Time Analysis
st.markdown("---")
st.subheader("📈 LinqAlpha Response Time Analysis")

# 데이터 전처리
df_time = df_all.copy()
# 이상치 처리
df_time.loc[df_time['time_to_first_byte'] <= 0, 'time_to_first_byte'] = None
df_time.loc[df_time['time_to_first_byte'] > 300000, 'time_to_first_byte'] = None  # 5분 초과 제거

# ms를 초로 변환
df_time['time_to_first_byte'] = df_time['time_to_first_byte'] / 1000

# 기본 통계량 표시
col1, col2, col3 = st.columns(3)
with col1:
    median_time = df_time['time_to_first_byte'].median()
    st.metric("Median Response Time", f"{median_time:.1f} sec")
with col2:
    mean_time = df_time['time_to_first_byte'].mean()
    st.metric("Average Response Time", f"{mean_time:.1f} sec")
with col3:
    p95_time = df_time['time_to_first_byte'].quantile(0.95)
    st.metric("95th Percentile", f"{p95_time:.1f} sec")

# Matplotlib을 사용한 시계열 시각화
plt.style.use('seaborn')
fig_mpl, ax = plt.subplots(figsize=(12, 6))

# 시계열 데이터 준비
df_time['date'] = df_time['created_at'].dt.date
daily_stats = df_time.groupby('date').agg({
    'time_to_first_byte': 'median',
    'id': 'count'
}).reset_index()

# 2025년 4월 1일 이후, 오늘 제외 데이터만 필터링
start_date = pd.Timestamp('2025-04-01').date()
end_date = pd.Timestamp.now().date() - pd.Timedelta(days=1)
daily_stats = daily_stats[
    (daily_stats['date'] >= start_date) & 
    (daily_stats['date'] <= end_date)
]

# 시계열 플롯
ax.plot(daily_stats['date'], daily_stats['time_to_first_byte'], 
        marker='o', linestyle='-', linewidth=2, markersize=6)

# 축 레이블과 제목
ax.set_xlabel('Date')
ax.set_ylabel('Response Time (seconds)')
ax.set_title('Daily Median Response Time (Matplotlib)')

# x축 날짜 포맷 조정
plt.xticks(rotation=45)
plt.tight_layout()

# Streamlit에 Matplotlib 차트 표시
st.pyplot(fig_mpl)


# 날짜 선택기 추가
available_dates = sorted(daily_stats['date'].unique(), reverse=True)  # 내림차순 정렬
selected_date = st.selectbox(
    "Select a date to see detailed statistics",
    [""] + [d.strftime("%Y-%m-%d") for d in available_dates],
    index=0
)

# 선택된 날짜가 있을 경우에만 상세 통계 표시
if selected_date:
    selected_date = pd.to_datetime(selected_date).date()
    selected_date_data = df_time[df_time['date'] == selected_date].copy()
    
    st.markdown(f"### 📊 Detailed Analysis for {selected_date}")
    
    # Function별 통계 테이블 먼저 계산
    func_stats = selected_date_data.groupby('agent_type').agg({
        'time_to_first_byte': ['count', 'mean', 'median', 'max']
    }).round(1)
    func_stats.columns = ['Count', 'Mean (sec)', 'Median (sec)', 'Max (sec)']
    
    # 원본 데이터 수와 필터링된 데이터 수 계산
    total_raw_requests = len(selected_date_data)
    valid_requests = func_stats['Count'].sum()
    
    # 기본 통계
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Total Requests",
            f"{total_raw_requests} ({valid_requests} valid)",
            help="Total number of requests (number of requests with valid response time)"
        )
    with col2:
        st.metric("Median Response Time", f"{selected_date_data['time_to_first_byte'].median():.1f} sec")
    with col3:
        st.metric("Mean Response Time", f"{selected_date_data['time_to_first_byte'].mean():.1f} sec")
    with col4:
        st.metric("Max Response Time", f"{selected_date_data['time_to_first_byte'].max():.1f} sec")

    # Function별 통계 테이블 열 순서 변경
    func_stats = func_stats[['Count', 'Median (sec)', 'Mean (sec)', 'Max (sec)']]
    func_stats = func_stats.sort_values('Count', ascending=False)
    
    # 0을 '-'로 대체
    func_stats = func_stats.replace(0, '-')
    
    st.markdown("#### Function Statistics")
    st.dataframe(func_stats.astype(object), use_container_width=True)

    # Slow Requests (상위 10개)
    st.markdown("#### Slowest Requests")
    slow_requests = selected_date_data.nlargest(10, 'time_to_first_byte')[
        ['created_at', 'agent_type', 'time_to_first_byte', 'id']
    ].copy()
    slow_requests['created_at'] = slow_requests['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
    slow_requests.columns = ['Timestamp', 'Function', 'Response Time (sec)', 'Request ID']
    slow_requests = slow_requests.sort_values('Response Time (sec)', ascending=False)
    st.dataframe(slow_requests, use_container_width=True)

# 두 번째 줄: 히스토그램과 도표
left_col, right_col = st.columns([3, 2])  # 히스토그램이 더 넓게

with left_col:
    # 히스토그램
    fig2 = px.histogram(
        df_time,
        x='time_to_first_byte',
        nbins=50,
        title='Distribution of Response Times',
        labels={'time_to_first_byte': 'Response Time (seconds)', 'count': 'Number of Requests'}
    )
    
    # 중앙값과 평균값 표시선 추가
    fig2.add_vline(
        x=median_time,
        line=dict(color="red", width=2, dash="dash"),
        annotation_text=f"Median: {median_time:.1f}s",
        annotation_position="top",
        annotation=dict(font=dict(color="red"))
    )
    fig2.add_vline(
        x=mean_time,
        line=dict(color="green", width=2, dash="dash"),
        annotation_text=f"Mean: {mean_time:.1f}s",
        annotation_position="bottom",
        annotation=dict(font=dict(color="green"))
    )
    
    fig2.update_layout(
        height=400,
        bargap=0.1,
        showlegend=True
    )
    st.plotly_chart(fig2, use_container_width=True)

with right_col:
    # 함수별 응답 시간 (Count 기준 내림차순 정렬)
    st.markdown("### 🔍 Response Time by Function")
    func_stats = df_time.groupby('agent_type')['time_to_first_byte'].agg([
        'mean', 'median', 'count'
    ]).reset_index()
    func_stats.columns = ['Function', 'Mean (sec)', 'Median (sec)', 'Count']
    func_stats = func_stats.sort_values('Count', ascending=False)  # Count 기준 내림차순
    
    # 0을 '-'로 대체
    func_stats = func_stats.replace(0, '-')
    
    st.dataframe(func_stats.round(2).astype(object), use_container_width=True, hide_index=True)  # hide_index=True 추가

