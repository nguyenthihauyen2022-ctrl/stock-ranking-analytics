import streamlit as st
import pandas as pd


def page_header(title, description=None):
    st.title(title)

    if description:
        st.caption(description)


def metric_card(
    label,
    value,
    help_text=None
):
    st.metric(
        label=label,
        value=value,
        help=help_text
    )


def format_number(
    value,
    digits=2
):
    if pd.isna(value):
        return "—"

    return f"{value:,.{digits}f}"


def format_percent(
    value,
    digits=2
):
    if pd.isna(value):
        return "—"

    return f"{value * 100:,.{digits}f}%"


def show_data_warning(message):
    st.warning(message)


def show_data_source():
    st.caption(
        "Nguồn dữ liệu: SSI FastConnect API | "
        "Lưu trữ: SQLite | "
        "Phân tích: dữ liệu giá và giao dịch"
    )


def show_empty_state(message):
    st.info(message)
    