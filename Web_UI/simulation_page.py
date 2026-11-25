import time

from dash import html

def layout(lang: str = "vi"):
    # Cache-bust ?v=<ts>: trang này đang sửa liên tục trong phiên này — nếu
    # src giữ NGUYÊN giữa các lần vào trang, Dash không tạo lại iframe (React
    # giữ DOM node cũ), trình duyệt không fetch lại dù server đã có bản mới
    # (ngay cả với Cache-Control: no-cache — vấn đề là KHÔNG CÓ request mới
    # nào được gửi, không phải do cache). Tính lại mỗi lần layout() được gọi
    # (mỗi lần điều hướng tới trang) để LUÔN ép tải lại bản mới nhất.
    v = int(time.time())
    return html.Div(
        html.Iframe(
            src=f"/assets/simulation.html?lang={lang}&v={v}",
            style={
                "width": "100%",
                "height": "calc(100vh - 68px)",
                "border": "none",
                "borderRadius": "12px",
            }
        ),
        style={"width": "100%", "height": "100%", "padding": "4px 8px 4px 8px"}
    )
