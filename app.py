import streamlit as st

pg = st.navigation(
    [
        st.Page("dashboard.py", title="Smart Money Flow", icon="💹", default=True),
        st.Page("bottom.py", title="Bitcoin Bottom Signal", icon="🟠", url_path="bottom"),
    ],
    position="top",
)
pg.run()
