import streamlit as st
import pandas as pd
import numpy as np
import random
from google.oauth2 import service_account
from google.cloud import bigquery
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

st.set_page_config(page_title="Voters Panel", layout="wide")
st.title("📊 Voters panel")

@st.cache_resource
def get_credentials():
    return service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )

@st.cache_resource
def create_client():
    credentials = get_credentials()
    return bigquery.Client(credentials=credentials, project=credentials.project_id)

client = create_client()

st.sidebar.header("🔧 Data")

# Proje seçimi
projects = client.list_projects()
project_names = [p.project_id for p in projects]
selected_project = st.sidebar.selectbox("Proyekt", project_names, key="selected_project")

# Dataset seçimi
datasets = list(client.list_datasets(selected_project))
dataset_names = [d.dataset_id for d in datasets]
selected_dataset = st.sidebar.selectbox("Dataset", dataset_names, key="selected_dataset")

# Tablo seçimi
tables = list(client.list_tables(f"{selected_project}.{selected_dataset}"))
table_names = [t.table_id for t in tables]
selected_table = st.sidebar.selectbox("Table", table_names, key="selected_table")

# 🔄 Seçimler değiştiğinde sıfırla ve yenile
if "prev_selected_project" not in st.session_state:
    st.session_state.prev_selected_project = selected_project
if "prev_selected_dataset" not in st.session_state:
    st.session_state.prev_selected_dataset = selected_dataset
if "prev_selected_table" not in st.session_state:
    st.session_state.prev_selected_table = selected_table

if (st.session_state.prev_selected_project != selected_project or
    st.session_state.prev_selected_dataset != selected_dataset or
    st.session_state.prev_selected_table != selected_table):
    
    st.session_state.prev_selected_project = selected_project
    st.session_state.prev_selected_dataset = selected_dataset
    st.session_state.prev_selected_table = selected_table

    st.session_state.offset = 0
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📑 Bir istəktə qəbul edilən sətir sayı")
rows_per_page = st.sidebar.number_input("Görünən sətir sayı", min_value=10, max_value=999999, value=3000, step=10)

if "offset" not in st.session_state:
    st.session_state.offset = 0
offset = st.session_state.offset

@st.cache_data(ttl=600)
def get_total_rows():
    query = f"SELECT COUNT(*) as total FROM {selected_project}.{selected_dataset}.{selected_table}"
    return client.query(query).to_dataframe().iloc[0]['total']

total_rows = get_total_rows()
current_page = (offset // rows_per_page) + 1
total_pages = int(np.ceil(total_rows / rows_per_page))

def load_next_page():
    if st.session_state.offset + rows_per_page < total_rows:
        st.session_state.offset += rows_per_page

def load_prev_page():
    st.session_state.offset = max(0, st.session_state.offset - rows_per_page)

st.sidebar.markdown("---")
st.sidebar.subheader("📄 Pagination")
col1, col2 = st.sidebar.columns(2)

with col1:
    if st.button("⬅️ Geri"):
        load_prev_page()
with col2:
    if st.button("İrəli ➡️"):
        load_next_page()

st.sidebar.markdown(f"**Səhifə:** {current_page} / {total_pages}")

@st.cache_data(ttl=600)
def get_page_data(offset, limit, search_query):
    base_query = f"SELECT * FROM {selected_project}.{selected_dataset}.{selected_table}"
    
    if search_query:
        keywords = search_query.split()
        conditions = [f"(LOWER(soyad) LIKE '%{k.lower()}%' OR LOWER(ad) LIKE '%{k.lower()}%' OR LOWER(ata_adi) LIKE '%{k.lower()}%')" for k in keywords]
        where_clause = " AND ".join(conditions)
        query = f"{base_query} WHERE {where_clause} LIMIT {limit} OFFSET {offset}"
    else:
        query = f"{base_query} LIMIT {limit} OFFSET {offset}"
    
    df = client.query(query).to_dataframe()
    df.columns = df.columns.str.lower()
    return df

search_query = st.text_input("🔍 Search", placeholder="Axtarış")
df = get_page_data(offset, rows_per_page, search_query)

st.markdown(f"**Cəmi sətir sayı:** {int(total_rows)} | Göstərilən: {rows_per_page} sətir | Səhifə: {current_page} / {total_pages}")

with st.expander("📝Sütun adlarını dəyişdir"):
    rename_map = {}
    for col in df.columns:
        new_name = st.text_input(f"{col} Sütunun yeni adı:", value=col, key=f"rename_{col}")
        rename_map[col] = new_name
    df.rename(columns=rename_map, inplace=True)

gb = GridOptionsBuilder.from_dataframe(df)

if "id" in df.columns:
    gb.configure_column("id", editable=False)

gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=rows_per_page)
gb.configure_selection("single")
gb.configure_default_column(
    filter=True,
    sortable=True,
    editable=False,
    resizable=True,
    enableRowGroup=True,
    enablePivot=True,
    enableValue=True,
    menuTabs=["generalMenuTab", "filterMenuTab"]
)

grid_options = gb.build()
grid_options["sideBar"] = {
    "toolPanels": [
        {
            "id": "columns",
            "labelDefault": "Columns",
            "labelKey": "columns",
            "iconKey": "columns",
            "toolPanel": "agColumnsToolPanel",
        }
    ],
    "defaultToolPanel": ""
}

custom_css = {
    ".ag-header-cell-label": {"font-size": "16px"},
    ".ag-cell": {"font-size": "15px"},
    ".ag-theme-streamlit": {"font-family": "Arial, sans-serif"},
}

grid_response = AgGrid(
    df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    height=600,
    fit_columns_on_grid_load=True,
    custom_css=custom_css
)

# ... kalan insert / update / delete işlemleri burada olduğu gibi devam eder ...



selected_rows = grid_response["selected_rows"]

selected = None
if isinstance(selected_rows, list) and len(selected_rows) > 0:
    selected = selected_rows[0]
elif hasattr(selected_rows, "iloc") and not selected_rows.empty:
    selected = selected_rows.iloc[0].to_dict()

if selected:
    st.markdown("---")
    st.subheader("🧾 Seçilmiş şəxs detalları")

    with st.form("edit_form"):
        updated_data = {}
        for key, value in selected.items():
            if key == "id":
                st.text(f"{key}: {value}")
                continue
            updated_data[key] = st.text_input(f"{key}:", value=str(value))

        submitted = st.form_submit_button("💾 Dəyişiklikləri yadda saxla")

        if submitted:
            try:
                def update_row_in_bigquery(project, dataset, table, primary_key, primary_value, updated_data):
                    set_clauses = [f"{key} = @{key}" for key in updated_data if key != primary_key]
                    set_clause = ", ".join(set_clauses)

                    query = f"""
                        UPDATE {project}.{dataset}.{table}
                        SET {set_clause}
                        WHERE {primary_key} = @primary_value
                    """

                    job_config = bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter("primary_value", "INT64", int(primary_value))
                        ] + [
                            bigquery.ScalarQueryParameter(key, "STRING", updated_data[key])
                            for key in updated_data if key != primary_key
                        ]
                    )

                    client.query(query, job_config=job_config).result()

                primary_key = "id"
                primary_value = selected[primary_key]

                update_row_in_bigquery(
                    selected_project,
                    selected_dataset,
                    selected_table,
                    primary_key,
                    primary_value,
                    updated_data
                )

                st.success("✅ Məlumatlar uğurla güncəlləndi.")
                st.cache_data.clear()  # 💥 Güncellenen verileri göstermek için cache'i temizliyoruz
                st.rerun()

            except Exception as e:
                st.error(f"❌ Güncəlləmə zamanı xəta baş verdi: {e}")

csv_data = df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ CSV Olaraq Yüklə", data=csv_data, file_name=f"{selected_table}_veriler.csv", mime="text/csv")

with st.expander("➕ Yeni şəxs əlavə et"):
    st.subheader("🧍 Yeni şəxs məlumatları")

    new_data = {}
    fields = [
        "SOYAD", "AD", "ATA_ADI", "CiNS", "DOGUM_TARiXi", "RAYON", "ICMA",
        "BOLGE", "UNVAN", "VALUE", "VALUE1", "VEZiFE"
    ]

    with st.form("add_form"):
        for field in fields:
            new_data[field] = st.text_input(f"{field}:")

        submitted = st.form_submit_button("📤 Əlavə et")

        if submitted:
            try:
                def insert_row_in_bigquery(project, dataset, table, row_data):
                    row_data["id"] = random.randint(10000000, 99999999)  # Rastgele ID oluştur
                    keys = ", ".join(row_data.keys())
                    values = ", ".join([f"@{k}" for k in row_data.keys()])

                    query = f"""
                        INSERT INTO `{project}.{dataset}.{table}` ({keys})
                        VALUES ({values})
                    """

                    job_config = bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter(k, "STRING" if k != "id" else "INT64", v if k != "id" else int(v))
                            for k, v in row_data.items()
                        ]
                    )

                    client.query(query, job_config=job_config).result()

                insert_row_in_bigquery(selected_project, selected_dataset, selected_table, new_data)
                st.success("✅ Yeni şəxs uğurla əlavə olundu.")
                st.cache_data.clear()
                st.rerun()

            except Exception as e:
                st.error(f"❌ Əlavə edilərkən xəta baş verdi: {e}")

if selected:
    st.markdown("### ❌ Seçilmiş sətiri sil")

    if st.button("🗑️ Bu şəxsi sil"):
        try:
            def delete_row_in_bigquery(project, dataset, table, primary_key, primary_value):
                query = f"""
                    DELETE FROM `{project}.{dataset}.{table}`
                    WHERE {primary_key} = @primary_value
                """
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("primary_value", "INT64", int(primary_value))
                    ]
                )
                client.query(query, job_config=job_config).result()

            primary_key = "id"
            primary_value = selected["id"]

            delete_row_in_bigquery(
                selected_project,
                selected_dataset,
                selected_table,
                primary_key,
                primary_value
            )

            st.success("✅ Sətir uğurla silindi.")
            st.cache_data.clear()
            st.rerun()

        except Exception as e:
            st.error(f"❌ Sətir silinərkən xəta baş verdi: {e}")

with st.expander("➕ Yeni sütun əlavə et"):
    st.subheader("🧱 Yeni sütun məlumatları")
    new_column_name = st.text_input("Sütun adı:", key="add_column_name")
    new_column_type = st.selectbox("Sütun tipi:", ["STRING", "INT64", "FLOAT64", "BOOL", "DATE", "TIMESTAMP"], key="add_column_type")

    if st.button("➕ Sütunu əlavə et"):
        if new_column_name:
            try:
                def add_column_to_bigquery(project, dataset, table, column_name, column_type):
                    query = f"""
                        ALTER TABLE `{project}.{dataset}.{table}`
                        ADD COLUMN {column_name} {column_type}
                    """
                    client.query(query).result()

                add_column_to_bigquery(selected_project, selected_dataset, selected_table, new_column_name, new_column_type)
                st.success(f"✅ `{new_column_name}` sütunu əlavə olundu.")
                st.cache_data.clear()
                st.rerun()

            except Exception as e:
                st.error(f"❌ Sütun əlavə edilərkən xəta baş verdi: {e}")
        else:
            st.warning("Sütun adı boş ola bilməz.")

with st.expander("🗑️ Sütun sil"):
    st.subheader("🧯 Sütunları sil")

    protected_columns = ["id"]  # silinməməli olan sütunlar
    deletable_columns = [col for col in df.columns if col not in protected_columns]
    column_to_delete = st.selectbox("Silinəcək sütun:", deletable_columns)

    if st.button("❌ Sütunu sil"):
        if column_to_delete:
            try:
                def delete_column_from_bigquery(project, dataset, table, column_name):
                    query = f"""
                        ALTER TABLE `{project}.{dataset}.{table}`
                        DROP COLUMN {column_name}
                    """
                    client.query(query).result()

                delete_column_from_bigquery(selected_project, selected_dataset, selected_table, column_to_delete)
                st.success(f"✅ `{column_to_delete}` sütunu silindi.")
                st.cache_data.clear()
                st.rerun()

            except Exception as e:
                st.error(f"❌ Sütun silinərkən xəta baş verdi: {e}")
