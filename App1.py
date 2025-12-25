import os
import subprocess
import sys

# FORCE INSTALL: If the library is missing, install it right now
try:
    import extra_streamlit_components
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "extra-streamlit-components"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit-option-menu"])

# ... Now continue with your normal imports ...
import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime, timedelta
import time
import extra_streamlit_components as stx
from streamlit_option_menu import option_menu
import base64

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="TSRS Robotics Lab", 
    layout="wide", 
    page_icon="🤖",
    initial_sidebar_state="expanded"
)

DB_FILE = "robolab_kits.db"

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    /* 1. Main Background */
    .stApp { 
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); 
    }

    /* 2. Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa; 
        border-right: 4px solid #630812; 
    }
    
    section[data-testid="stSidebar"] .stMarkdown, 
    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3, 
    section[data-testid="stSidebar"] p {
        color: #000000 !important;
    }

    /* 3. Metric Cards */
    div[data-testid="metric-container"] { 
        background-color: #ffffff; 
        border-left: 6px solid #be1e2d; 
        padding: 15px; 
        border-radius: 10px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
    }

    /* 4. Header Banner */
    .lab-header { 
        background-color: #ffffff; 
        padding: 20px; 
        border-radius: 15px; 
        text-align: center; 
        margin-bottom: 30px; 
        border-bottom: 4px solid #be1e2d; 
        box-shadow: 0 4px 15px rgba(0,0,0,0.1); 
    }
    .lab-title { 
        color: #be1e2d; 
        font-size: 32px; 
        font-weight: 800; 
        margin: 0; 
    }
    .lab-subtitle { 
        color: #333; 
        font-size: 18px; 
        margin-top: 5px; 
    }
    
    /* 5. Buttons - Maroon */
    .stButton > button { 
        background-color: #630812; 
        color: white; 
        border: none; 
    }
    .stButton > button:hover { 
        background-color: #8a0b1a; 
        color: white; 
    }
    
    /* 6. Profile Image Styling */
    .profile-img {
        border-radius: 50%;
        border: 3px solid #630812;
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    </style>
""", unsafe_allow_html=True)

# --- SECURITY UTILS ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return True
    return False

def image_to_base64(uploaded_file):
    if uploaded_file is not None:
        bytes_data = uploaded_file.getvalue()
        return base64.b64encode(bytes_data).decode('utf-8')
    return None

# --- COOKIE MANAGER ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

# --- DATABASE MANAGEMENT ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT, quantity INTEGER, threshold INTEGER, location TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, item_name TEXT, user TEXT, type TEXT, qty_change INTEGER, date TIMESTAMP, note TEXT)''')
    
    # Updated Users Table: Added employee_id, full_name, avatar
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, employee_id TEXT, full_name TEXT, avatar TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS kits (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, description TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS kit_contents (id INTEGER PRIMARY KEY AUTOINCREMENT, kit_id INTEGER, item_id INTEGER, qty_needed INTEGER, FOREIGN KEY(kit_id) REFERENCES kits(id), FOREIGN KEY(item_id) REFERENCES items(id))''')
    
    # DB Migrations for existing systems
    try:
        c.execute("SELECT full_name FROM users LIMIT 1")
    except sqlite3.OperationalError:
        try: c.execute("ALTER TABLE users ADD COLUMN employee_id TEXT") 
        except: pass
        try: c.execute("ALTER TABLE users ADD COLUMN full_name TEXT") 
        except: pass
        try: c.execute("ALTER TABLE users ADD COLUMN avatar TEXT") 
        except: pass
    
    # Create Admin
    c.execute('SELECT * FROM users WHERE username = "admin"')
    if not c.fetchone():
        c.execute('INSERT INTO users (username, password, role, full_name, employee_id) VALUES (?,?,?,?,?)', 
                  ("admin", make_hashes("admin123"), "admin", "System Administrator", "ADM001"))
    conn.commit()
    conn.close()

def run_query(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(query, params)
        if query.lower().strip().startswith("select"):
            data = c.fetchall()
            return data
        else:
            conn.commit()
            return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

init_db()

# --- HELPER FUNCTIONS ---
def get_kit_details(kit_id):
    query = "SELECT i.name, k.qty_needed, i.quantity as current_stock, i.id FROM kit_contents k JOIN items i ON k.item_id = i.id WHERE k.kit_id = ?"
    return run_query(query, (kit_id,))

def get_user_profile(username):
    # Returns: username, role, employee_id, full_name, avatar
    data = run_query("SELECT username, role, employee_id, full_name, avatar FROM users WHERE username = ?", (username,))
    if data:
        return data[0]
    return None

def render_header():
    st.markdown("""
        <div class="lab-header">
            <div class="lab-title">Robotics & AI Lab</div>
            <div class="lab-subtitle">TSRS-SAR | 2025 | Inventory Management System</div>
        </div>
    """, unsafe_allow_html=True)

# --- AUTHENTICATION ---
if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'user_role': None, 'username': None, 'avatar': None})

if not st.session_state['logged_in']:
    try:
        cookie_user = cookie_manager.get('robolab_user')
        if cookie_user:
            user_data = get_user_profile(cookie_user)
            if user_data:
                # user_data[4] is avatar
                st.session_state.update({'logged_in': True, 'username': user_data[0], 'user_role': user_data[1], 'avatar': user_data[4]})
    except Exception:
        pass

def login_page():
    render_header()
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.container():
            st.markdown("### 🔐 Secure Login")
            with st.form("login"):
                username = st.text_input("Username")
                password = st.text_input("Password", type='password')
                if st.form_submit_button("Access Lab Portal"):
                    users = run_query("SELECT password, role, avatar FROM users WHERE username = ?", (username,))
                    if users and check_hashes(password, users[0][0]):
                        expires = datetime.now() + timedelta(minutes=15)
                        cookie_manager.set('robolab_user', username, expires_at=expires)
                        st.session_state.update({'logged_in': True, 'username': username, 'user_role': users[0][1], 'avatar': users[0][2]})
                        st.rerun()
                    else:
                        st.error("Access Denied.")
            st.caption("Admin Default: `admin` / `admin123`")

def logout():
    try:
        cookie_manager.delete('robolab_user')
    except Exception:
        pass 
    st.session_state['logged_in'] = False
    st.session_state['user_role'] = None
    st.session_state['username'] = None
    st.session_state['avatar'] = None
    time.sleep(1)

# --- MAIN APP ---
if not st.session_state['logged_in']:
    login_page()
else:
    # --- SIDEBAR ---
    with st.sidebar:
        # Dynamic Avatar
        if st.session_state['avatar']:
            st.markdown(f'<img src="data:image/png;base64,{st.session_state["avatar"]}" class="profile-img" width="100">', unsafe_allow_html=True)
        else:
            st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=80)
            
        st.markdown(f"<h3 style='text-align: center; color: black;'>{st.session_state['username']}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center; color: grey;'>{st.session_state['user_role'].upper()}</p>", unsafe_allow_html=True)
        st.write("---")
        
        # Menu
        if st.session_state['user_role'] == 'admin':
            opts = ["Dashboard", "Stock & Kits", "Manage Inventory", "Kit Builder", "Reports", "User Mgmt", "My Profile"]
            icons_list = ["speedometer2", "box-seam", "database", "tools", "file-earmark-bar-graph", "people", "person-circle"]
        else:
            opts = ["Dashboard", "Stock & Kits", "My Profile"]
            icons_list = ["speedometer2", "box-seam", "person-circle"]
        
        page = option_menu(
            menu_title=None,
            options=opts,
            icons=icons_list,
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "icon": {"color": "#630812", "font-size": "18px"},
                "nav-link": {"font-size": "16px", "text-align": "left", "margin":"5px", "color": "black", "--hover-color": "#eee"},
                "nav-link-selected": {"background-color": "#630812", "color": "white"}, 
            }
        )
        
        st.write("---")
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()

    render_header()

    # --- 1. DASHBOARD ---
    if page == "Dashboard":
        st.subheader("📊 Operational Overview")
        items_data = run_query("SELECT * FROM items")
        if items_data:
            items = pd.DataFrame(items_data, columns=['id', 'name', 'cat', 'qty', 'threshold', 'loc'])
            kits_count = run_query("SELECT count(*) FROM kits")[0][0]
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Components", len(items), "Items")
            c2.metric("Total Stock Volume", items['qty'].sum(), "Units")
            c3.metric("Active Kit Types", kits_count, "Activities")
            st.markdown("---")
            low_stock = items[items['qty'] <= items['threshold']].copy()
            c_left, c_right = st.columns([2, 1])
            with c_left:
                st.markdown("##### 📦 Stock Distribution")
                cat_chart = items.groupby("cat")["qty"].sum()
                st.bar_chart(cat_chart, color="#be1e2d")
            with c_right:
                 st.markdown("##### ⚠️ Low Stock Alerts")
                 if not low_stock.empty:
                     st.dataframe(low_stock[['name', 'qty', 'threshold']], hide_index=True)
                 else:
                     st.success("All stocks healthy.")
            st.markdown("---")
            st.subheader("📝 Purchase Requisition")
            if not low_stock.empty:
                st.info("Items below threshold:")
                low_stock['Recommended Order'] = (low_stock['threshold'] - low_stock['qty']) + 5
                req_df = low_stock[['name', 'category', 'qty', 'threshold', 'Recommended Order', 'location']]
                req_df.columns = ['Item Name', 'Category', 'Current Qty', 'Min Limit', 'To Buy', 'Location']
                st.dataframe(req_df, width='stretch')
                csv_data = req_df.to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Download Purchase Order", data=csv_data, file_name=f"PO_{datetime.now().strftime('%Y-%m-%d')}.csv", mime="text/csv", type="primary")
            else:
                st.success("✅ No Purchase Orders needed.")
        else:
            st.info("System Initialized. Please add inventory.")

    # --- 2. STOCK & KITS ---
    elif page == "Stock & Kits":
        st.subheader("📦 Inventory Counter")
        tab1, tab2 = st.tabs(["🧩 Issue Activity Kit", "🔧 Single Item Transaction"])
        with tab1:
            kits = run_query("SELECT id, name FROM kits")
            if kits:
                c_sel, c_act = st.columns([3, 1])
                kit_opts = {k[1]: k[0] for k in kits}
                sel_kit_name = c_sel.selectbox("Select Activity Kit", list(kit_opts.keys()))
                sel_kit_id = kit_opts[sel_kit_name]
                contents = get_kit_details(sel_kit_id)
                if contents:
                    df_kit = pd.DataFrame(contents, columns=['Component', 'Qty Per Kit', 'Current Stock', 'ID'])
                    st.dataframe(df_kit[['Component', 'Qty Per Kit', 'Current Stock']], width='stretch')
                    possible = True
                    for index, row in df_kit.iterrows():
                        if row['Qty Per Kit'] > row['Current Stock']:
                            possible = False
                            st.toast(f"Low Stock: {row['Component']}", icon="❌")
                    if possible and c_act.button(f"ISSUE KIT", type="primary"):
                        for index, row in df_kit.iterrows():
                            new_qty = row['Current Stock'] - row['Qty Per Kit']
                            run_query("UPDATE items SET quantity = ? WHERE id = ?", (new_qty, row['ID']))
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("INSERT INTO transactions (item_id, item_name, user, type, qty_change, date, note) VALUES (?,?,?,?,?,?,?)", (row['ID'], row['Component'], st.session_state['username'], "OUT", row['Qty Per Kit'], datetime.now(), f"Kit: {sel_kit_name}"))
                            conn.commit()
                            conn.close()
                        st.success(f"Successfully issued '{sel_kit_name}'")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Empty Kit.")
            else:
                st.info("No kits defined.")
        with tab2:
            st.markdown("#### Manage Single Component")
            items = run_query("SELECT id, name, quantity FROM items")
            if items:
                item_map = {i[1]: (i[0], i[2]) for i in items}
                sel_item = st.selectbox("Search Component", list(item_map.keys()))
                curr_id, curr_qty = item_map[sel_item]
                st.info(f"Current Stock: **{curr_qty}**")
                txn_note = st.text_input("Transaction Note / Remark", placeholder="e.g., Student Project, Broken Part")
                c1, c2 = st.columns(2)
                with c1:
                    qty_in = st.number_input("Receive (+)", min_value=1, key='in')
                    if st.button("Add to Stock"):
                        run_query("UPDATE items SET quantity = ? WHERE id = ?", (curr_qty + qty_in, curr_id))
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("INSERT INTO transactions (item_id, item_name, user, type, qty_change, date, note) VALUES (?,?,?,?,?,?,?)", (curr_id, sel_item, st.session_state['username'], "IN", qty_in, datetime.now(), txn_note or "Manual Restock"))
                        conn.commit()
                        conn.close()
                        st.success("Added!")
                        time.sleep(1)
                        st.rerun()
                with c2:
                    qty_out = st.number_input("Consume (-)", min_value=1, key='out')
                    if st.button("Deduct from Stock"):
                        if curr_qty >= qty_out:
                            run_query("UPDATE items SET quantity = ? WHERE id = ?", (curr_qty - qty_out, curr_id))
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("INSERT INTO transactions (item_id, item_name, user, type, qty_change, date, note) VALUES (?,?,?,?,?,?,?)", (curr_id, sel_item, st.session_state['username'], "OUT", qty_out, datetime.now(), txn_note or "Manual Usage"))
                            conn.commit()
                            conn.close()
                            st.success("Deducted!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Insufficient Stock")
            else:
                st.warning("Inventory is empty.")

    # --- 3. MANAGE INVENTORY ---
    elif page == "Manage Inventory":
        st.subheader("🗄️ Database Management")
        with st.expander("📤 Bulk Import (Excel/CSV)", expanded=False):
            st.info("Required Columns: `Name`, `Category`, `Quantity`, `Threshold`, `Location`")
            if st.button("Download Template CSV"):
                df_temp = pd.DataFrame(columns=["Name", "Category", "Quantity", "Threshold", "Location"])
                st.download_button("Get Template", df_temp.to_csv(index=False).encode('utf-8'), "template.csv", "text/csv")
            uploaded_file = st.file_uploader("Drop File Here", type=['xlsx', 'csv'])
            if uploaded_file and st.button("Process Import"):
                try:
                    df_import = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('csv') else pd.read_excel(uploaded_file)
                    df_import.fillna(0, inplace=True)
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    for index, row in df_import.iterrows():
                        name = str(row['Name']).strip()
                        qty = int(row['Quantity'])
                        thresh = int(row['Threshold'])
                        cat = str(row['Category'])
                        loc = str(row['Location'])
                        c.execute("SELECT quantity FROM items WHERE name=?", (name,))
                        exists = c.fetchone()
                        if exists:
                            c.execute("UPDATE items SET quantity=?, threshold=?, location=? WHERE name=?", (exists[0] + qty, thresh, loc, name))
                        else:
                            c.execute("INSERT INTO items (name, category, quantity, threshold, location) VALUES (?,?,?,?,?)", (name, cat, qty, thresh, loc))
                    conn.commit()
                    conn.close()
                    st.success("Import Complete!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        with st.expander("➕ Add Single Item", expanded=False):
            with st.form("new_item"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Item Name")
                cat = c2.selectbox("Category", ["Sensors", "Motors", "Microcontrollers", "Wires", "Tools", "Batteries", "Other"])
                c3, c4, c5 = st.columns(3)
                qty = c3.number_input("Qty", min_value=0)
                thresh = c4.number_input("Threshold", value=5)
                loc = c5.text_input("Location")
                if st.form_submit_button("Save"):
                    if run_query("INSERT INTO items (name, category, quantity, threshold, location) VALUES (?,?,?,?,?)", (name, cat, qty, thresh, loc)):
                        st.success("Added!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Item exists.")
        data = run_query("SELECT * FROM items")
        if data:
            st.dataframe(pd.DataFrame(data, columns=['ID', 'Name', 'Category', 'Qty', 'Threshold', 'Location']), width='stretch')

    # --- 4. KIT BUILDER ---
    elif page == "Kit Builder":
        st.subheader("🧰 Kit Configuration")
        c1, c2 = st.columns([1, 2])
        with c1:
            with st.form("create_kit"):
                st.markdown("#### Create Kit Type")
                new_kit = st.text_input("Kit Name")
                desc = st.text_input("Description")
                if st.form_submit_button("Create"):
                    if run_query("INSERT INTO kits (name, description) VALUES (?,?)", (new_kit, desc)):
                        st.success("Created!")
                        st.rerun()
        with c2:
            st.markdown("#### Add Contents")
            kits = run_query("SELECT id, name FROM kits")
            items = run_query("SELECT id, name FROM items")
            if kits and items:
                k_col, i_col, q_col = st.columns(3)
                kit_map = {k[1]: k[0] for k in kits}
                sel_kit = k_col.selectbox("Kit", list(kit_map.keys()))
                item_map = {i[1]: i[0] for i in items}
                sel_item = i_col.selectbox("Component", list(item_map.keys()))
                qty_needed = q_col.number_input("Qty", min_value=1, value=1)
                if st.button("Link Item"):
                    run_query("INSERT INTO kit_contents (kit_id, item_id, qty_needed) VALUES (?,?,?)", (kit_map[sel_kit], item_map[sel_item], qty_needed))
                    st.success("Linked!")
                    time.sleep(0.5)
                    st.rerun()
                st.divider()
                st.caption(f"Contents of: {sel_kit}")
                contents = get_kit_details(kit_map[sel_kit])
                if contents:
                    st.dataframe(pd.DataFrame(contents, columns=['Component', 'Qty Needed', 'Stock', 'ID'])[['Component', 'Qty Needed']], width='stretch')

    # --- 5. REPORTS ---
    elif page == "Reports":
        st.subheader("📑 Audit & Usage Reports")
        data = run_query("SELECT * FROM transactions ORDER BY date DESC")
        if data:
            df = pd.DataFrame(data, columns=['ID', 'Item ID', 'Item', 'User', 'Type', 'Qty', 'Date', 'Note'])
            df['Date'] = pd.to_datetime(df['Date'])
            report_period = st.selectbox("Select Report Period", ["All Time", "Monthly (Last 30 Days)", "Quarterly (Last 90 Days)", "Half Yearly (Last 180 Days)", "Yearly (Last 365 Days)"])
            today = datetime.now()
            if report_period == "Monthly (Last 30 Days)":
                df = df[df['Date'] >= (today - timedelta(days=30))]
            elif report_period == "Quarterly (Last 90 Days)":
                df = df[df['Date'] >= (today - timedelta(days=90))]
            elif report_period == "Half Yearly (Last 180 Days)":
                df = df[df['Date'] >= (today - timedelta(days=180))]
            elif report_period == "Yearly (Last 365 Days)":
                df = df[df['Date'] >= (today - timedelta(days=365))]
            c1, c2 = st.columns(2)
            c1.metric("Items Consumed (OUT)", df[df['Type'] == 'OUT']['Qty'].sum())
            c2.metric("Items Restocked (IN)", df[df['Type'] == 'IN']['Qty'].sum())
            st.dataframe(df, width='stretch')
            st.download_button(f"Download {report_period} CSV", df.to_csv().encode('utf-8'), f"report_{report_period.lower()}.csv")
        else:
            st.info("No transaction history found.")

    # --- 6. USER MGMT ---
    elif page == "User Mgmt":
        st.subheader("👥 User Administration")
        with st.form("add_user"):
            st.markdown("##### Create New User")
            c1, c2 = st.columns(2)
            u = c1.text_input("Username")
            p = c2.text_input("Password", type="password")
            
            c3, c4, c5 = st.columns(3)
            r = c3.selectbox("Role", ["lab_assistant", "admin"])
            emp_id = c4.text_input("Employee ID (Unique)")
            fname = c5.text_input("Full Name")
            
            if st.form_submit_button("Register User"):
                if u and p and emp_id:
                    if run_query("INSERT INTO users (username, password, role, employee_id, full_name) VALUES (?,?,?,?,?)", (u, make_hashes(p), r, emp_id, fname)):
                        st.success(f"User {u} ({fname}) created successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Username already exists or database error.")
                else:
                    st.warning("Please fill all fields.")
        
        st.markdown("##### Existing Users")
        users = run_query("SELECT username, role, employee_id, full_name FROM users")
        if users:
            st.dataframe(pd.DataFrame(users, columns=['Username', 'Role', 'Emp ID', 'Full Name']), width='stretch')

    # --- 7. MY PROFILE ---
    elif page == "My Profile":
        st.subheader("👤 My Profile Settings")
        
        user_data = get_user_profile(st.session_state['username'])
        # user_data: (username, role, employee_id, full_name, avatar)
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown("#### Profile Picture")
            if user_data[4]:
                st.markdown(f'<img src="data:image/png;base64,{user_data[4]}" class="profile-img" width="150">', unsafe_allow_html=True)
            else:
                st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=150)
            st.markdown("<br>", unsafe_allow_html=True)
            uploaded_file = st.file_uploader("Change Avatar", type=['png', 'jpg', 'jpeg'])
            if uploaded_file is not None:
                if st.button("Save New Picture"):
                    img_str = image_to_base64(uploaded_file)
                    run_query("UPDATE users SET avatar = ? WHERE username = ?", (img_str, st.session_state['username']))
                    st.session_state['avatar'] = img_str
                    st.success("Avatar updated!")
                    time.sleep(1)
                    st.rerun()

        with col2:
            st.markdown("#### Personal Details")
            
            with st.form("update_details"):
                # Locked Employee ID
                st.text_input("Employee ID", value=user_data[2] if user_data[2] else "N/A", disabled=True)
                
                # Editable Full Name
                curr_name = user_data[3] if user_data[3] else ""
                new_name = st.text_input("Full Name", value=curr_name)
                
                if st.form_submit_button("Update Details"):
                    run_query("UPDATE users SET full_name = ? WHERE username = ?", (new_name, st.session_state['username']))
                    st.success("Details saved successfully.")
                    time.sleep(0.5)
                    st.rerun()

            st.divider()
            
            st.markdown("#### Security")
            with st.expander("Change Password"):
                with st.form("change_pass"):
                    old_pass = st.text_input("Current Password", type="password")
                    new_pass = st.text_input("New Password", type="password")
                    conf_pass = st.text_input("Confirm New Password", type="password")
                    
                    if st.form_submit_button("Update Password"):
                        current_hash = run_query("SELECT password FROM users WHERE username = ?", (st.session_state['username'],))[0][0]
                        if check_hashes(old_pass, current_hash):
                            if new_pass == conf_pass and new_pass != "":
                                run_query("UPDATE users SET password = ? WHERE username = ?", (make_hashes(new_pass), st.session_state['username']))
                                st.success("Password Changed Successfully!")
                            else:
                                st.error("New passwords do not match or are empty.")
                        else:
                            st.error("Incorrect Current Password.")