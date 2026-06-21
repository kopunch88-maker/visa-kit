#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pack 60.2 (Фаза 3, бэкенд) — выбор формата для архива «Скачать всё».
1) doc_convert.py → + convert_package_zip / _batch_docx_to_pdf / _write_pdf_pages
   (перезапись модуля superset-версией; docx→pdf одним батч-вызовом soffice).
2) render_package (applications.py): + ?format= и постобработка готового ZIP.
Идемпотентно, .bak602, pre-write py_compile, CRLF-aware.
"""
import os, sys, base64, py_compile, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DC_B64 = "IyAtKi0gY29kaW5nOiB1dGYtOCAtKi0KIiIiClBhY2sgNjAuMCDigJQg0LrQvtC90LLQtdGA0YLQsNGG0LjRjyDQs9C+0YLQvtCy0L7Qs9C+INC00L7QutGD0LzQtdC90YLQsCDQsiDRhNC+0YDQvNCw0YIg0YHQutCw0YfQuNCy0LDQvdC40Y8uCgrQmNGB0YLQvtGH0L3QuNC6IChkb2N4IHwgcGRmKSDihpIgZG9jeCB8IHBkZiB8IGpwZWcoemlwKS4KICAtIGRvY3jihpJwZGYgIDogTGlicmVPZmZpY2UgKHNvZmZpY2UgLS1oZWFkbGVzcyAtLWNvbnZlcnQtdG8gcGRmKSDigJQg0YPQttC1INC90LAg0YHQtdGA0LLQtdGA0LUgKFBhY2sgNTIpLgogIC0gKuKGkmpwZWcgICAgOiBQREYg0YDQsNGB0YLQtdGA0LjQt9GD0LXRgtGB0Y8g0L/QvtGB0YLRgNCw0L3QuNGH0L3QviDRh9C10YDQtdC3IFB5TXVQREYgKGZpdHopOyDQutCw0LbQtNCw0Y8g0YHRgtGA0LDQvdC40YbQsCA9IEpQRUc7INCy0YHRkSDQsiBaSVAuCiAgLSBwZGbihpJkb2N4ICA6INCd0JUg0L/QvtC00LTQtdGA0LbQuNCy0LDQtdGC0YHRjyAo0YMg0L3QsNGC0LjQstC90YvRhSBQREYg0L3QtdGCIFdvcmQt0LjRgdGF0L7QtNC90LjQutCwKSDihpIgVmFsdWVFcnJvci4KIiIiCmltcG9ydCBpbwppbXBvcnQgb3MKaW1wb3J0IHN1YnByb2Nlc3MKaW1wb3J0IHRlbXBmaWxlCmltcG9ydCB6aXBmaWxlCgpET0NYX01FRElBID0gImFwcGxpY2F0aW9uL3ZuZC5vcGVueG1sZm9ybWF0cy1vZmZpY2Vkb2N1bWVudC53b3JkcHJvY2Vzc2luZ21sLmRvY3VtZW50IgpQREZfTUVESUEgPSAiYXBwbGljYXRpb24vcGRmIgpaSVBfTUVESUEgPSAiYXBwbGljYXRpb24vemlwIgoKCmRlZiBkb2N4X3RvX3BkZihkb2N4X2J5dGVzOiBieXRlcywgdGltZW91dF9zZWM6IGludCA9IDkwKSAtPiBieXRlczoKICAgICIiIkRPQ1gg4oaSIFBERiDRh9C10YDQtdC3IExpYnJlT2ZmaWNlIGhlYWRsZXNzICjRgtC+0YIg0LbQtSDQv9GD0YLRjCwg0YfRgtC+INGDINCy0YvQv9C40YHQutC4LCBQYWNrIDUyKS4iIiIKICAgIHdpdGggdGVtcGZpbGUuVGVtcG9yYXJ5RGlyZWN0b3J5KHByZWZpeD0idmtfY29udl8iKSBhcyB0bXA6CiAgICAgICAgc3JjID0gb3MucGF0aC5qb2luKHRtcCwgImRvYy5kb2N4IikKICAgICAgICB3aXRoIG9wZW4oc3JjLCAid2IiKSBhcyBmOgogICAgICAgICAgICBmLndyaXRlKGRvY3hfYnl0ZXMpCiAgICAgICAgdHJ5OgogICAgICAgICAgICByZXN1bHQgPSBzdWJwcm9jZXNzLnJ1bigKICAgICAgICAgICAgICAgIFsic29mZmljZSIsICItLWhlYWRsZXNzIiwgIi0tY29udmVydC10byIsICJwZGYiLCAiLS1vdXRkaXIiLCB0bXAsIHNyY10sCiAgICAgICAgICAgICAgICBjYXB0dXJlX291dHB1dD1UcnVlLCB0aW1lb3V0PXRpbWVvdXRfc2VjLAogICAgICAgICAgICApCiAgICAgICAgZXhjZXB0IEZpbGVOb3RGb3VuZEVycm9yOgogICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoIkxpYnJlT2ZmaWNlIChzb2ZmaWNlKSDQvdC1INC90LDQudC00LXQvSDQsiBQQVRILiIpCiAgICAgICAgZXhjZXB0IHN1YnByb2Nlc3MuVGltZW91dEV4cGlyZWQ6CiAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcihmIkxpYnJlT2ZmaWNlINC/0YDQtdCy0YvRgdC40Lsge3RpbWVvdXRfc2VjfSDRgdC10Log0L/RgNC4IGRvY3jihpJwZGYuIikKICAgICAgICBpZiByZXN1bHQucmV0dXJuY29kZSAhPSAwOgogICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoIkxpYnJlT2ZmaWNlIGRvY3jihpJwZGY6ICIgKyByZXN1bHQuc3RkZXJyLmRlY29kZSgidXRmLTgiLCAicmVwbGFjZSIpWzo1MDBdKQogICAgICAgIHBkZl9wYXRoID0gb3MucGF0aC5qb2luKHRtcCwgImRvYy5wZGYiKQogICAgICAgIGlmIG5vdCBvcy5wYXRoLmV4aXN0cyhwZGZfcGF0aCk6CiAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcigiUERGINC90LUg0L/QvtGP0LLQuNC70YHRjyDQv9C+0YHQu9C1INC60L7QvdCy0LXRgNGC0LDRhtC40LggZG9jeOKGknBkZi4iKQogICAgICAgIHdpdGggb3BlbihwZGZfcGF0aCwgInJiIikgYXMgZjoKICAgICAgICAgICAgcmV0dXJuIGYucmVhZCgpCgoKZGVmIHBkZl90b19qcGVnX3ppcChwZGZfYnl0ZXM6IGJ5dGVzLCBiYXNlX25hbWU6IHN0ciwgZHBpOiBpbnQgPSAxNzAsIHF1YWxpdHk6IGludCA9IDg1KSAtPiBieXRlczoKICAgICIiIlBERiDihpIgWklQINC/0L7RgdGC0YDQsNC90LjRh9C90YvRhSBKUEVHLiDQmtCw0LbQtNCw0Y8g0YHRgtGA0LDQvdC40YbQsDogPGJhc2VfbmFtZT5f0YHRgtGAMDEuanBnIC4uLiIiIgogICAgaW1wb3J0IGZpdHogICMgUHlNdVBERgogICAgem9vbSA9IGRwaSAvIDcyLjAKICAgIG1hdCA9IGZpdHouTWF0cml4KHpvb20sIHpvb20pCiAgICBvdXQgPSBpby5CeXRlc0lPKCkKICAgIGRvYyA9IGZpdHoub3BlbihzdHJlYW09cGRmX2J5dGVzLCBmaWxldHlwZT0icGRmIikKICAgIHRyeToKICAgICAgICBuID0gZG9jLnBhZ2VfY291bnQKICAgICAgICBwYWQgPSBtYXgoMiwgbGVuKHN0cihuKSkpCiAgICAgICAgd2l0aCB6aXBmaWxlLlppcEZpbGUob3V0LCAidyIsIHppcGZpbGUuWklQX0RFRkxBVEVEKSBhcyB6ZjoKICAgICAgICAgICAgZm9yIGkgaW4gcmFuZ2Uobik6CiAgICAgICAgICAgICAgICBwaXggPSBkb2MubG9hZF9wYWdlKGkpLmdldF9waXhtYXAobWF0cml4PW1hdCkKICAgICAgICAgICAgICAgIGpwZyA9IHBpeC50b2J5dGVzKCJqcGVnIiwganBnX3F1YWxpdHk9cXVhbGl0eSkKICAgICAgICAgICAgICAgIHpmLndyaXRlc3RyKGYie2Jhc2VfbmFtZX1f0YHRgtGAe3N0cihpICsgMSkuemZpbGwocGFkKX0uanBnIiwganBnKQogICAgZmluYWxseToKICAgICAgICBkb2MuY2xvc2UoKQogICAgcmV0dXJuIG91dC5nZXR2YWx1ZSgpCgoKZGVmIGNvbnZlcnQoY29udGVudDogYnl0ZXMsIHNyY19mbXQ6IHN0ciwgdGFyZ2V0X2ZtdDogc3RyLCBiYXNlX25hbWU6IHN0cik6CiAgICAiIiIKICAgINCS0L7Qt9Cy0YDQsNGJ0LDQtdGCIChieXRlcywgZmlsZW5hbWUsIG1lZGlhX3R5cGUpLgogICAgc3JjX2ZtdCAvIHRhcmdldF9mbXQg4oiIIHsnZG9jeCcsJ3BkZicsJ2pwZWcnfSAoKyDRgdC40L3QvtC90LjQvNGLIGpwZy9pbWFnZS9pbWFnZXMpLgogICAgYmFzZV9uYW1lIOKAlCDQsdC10Lcg0YDQsNGB0YjQuNGA0LXQvdC40Y8uCiAgICAiIiIKICAgIHNyY19mbXQgPSAoc3JjX2ZtdCBvciAiIikubG93ZXIoKQogICAgdCA9ICh0YXJnZXRfZm10IG9yICIiKS5sb3dlcigpCiAgICBpZiB0IGluICgianBnIiwgImltYWdlIiwgImltYWdlcyIpOgogICAgICAgIHQgPSAianBlZyIKCiAgICBpZiB0IGluICgiIiwgIm5hdGl2ZSIsIHNyY19mbXQpOgogICAgICAgIG1lZGlhID0gRE9DWF9NRURJQSBpZiBzcmNfZm10ID09ICJkb2N4IiBlbHNlIFBERl9NRURJQQogICAgICAgIHJldHVybiBjb250ZW50LCBmIntiYXNlX25hbWV9LntzcmNfZm10fSIsIG1lZGlhCgogICAgaWYgdCA9PSAicGRmIjoKICAgICAgICBpZiBzcmNfZm10ID09ICJkb2N4IjoKICAgICAgICAgICAgcmV0dXJuIGRvY3hfdG9fcGRmKGNvbnRlbnQpLCBmIntiYXNlX25hbWV9LnBkZiIsIFBERl9NRURJQQogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlBERiDQuNC3INGN0YLQvtCz0L4g0LjRgdGC0L7Rh9C90LjQutCwINC90LXQtNC+0YHRgtGD0L/QtdC9IikKCiAgICBpZiB0ID09ICJkb2N4IjoKICAgICAgICBpZiBzcmNfZm10ID09ICJkb2N4IjoKICAgICAgICAgICAgcmV0dXJuIGNvbnRlbnQsIGYie2Jhc2VfbmFtZX0uZG9jeCIsIERPQ1hfTUVESUEKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJXb3JkINC90LXQtNC+0YHRgtGD0L/QtdC9OiDRgyDQtNC+0LrRg9C80LXQvdGC0LAg0L3QtdGCIFdvcmQt0LjRgdGF0L7QtNC90LjQutCwICjQvtC9INC40LfQvdCw0YfQsNC70YzQvdC+IFBERikiKQoKICAgIGlmIHQgPT0gImpwZWciOgogICAgICAgIHBkZiA9IGNvbnRlbnQgaWYgc3JjX2ZtdCA9PSAicGRmIiBlbHNlIGRvY3hfdG9fcGRmKGNvbnRlbnQpCiAgICAgICAgcmV0dXJuIHBkZl90b19qcGVnX3ppcChwZGYsIGJhc2VfbmFtZSksIGYie2Jhc2VfbmFtZX1faW1hZ2VzLnppcCIsIFpJUF9NRURJQQoKICAgIHJhaXNlIFZhbHVlRXJyb3IoZiLQndC10LjQt9Cy0LXRgdGC0L3Ri9C5INGE0L7RgNC80LDRgjoge3RhcmdldF9mbXR9IikKCgojID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KIyBQYWNrIDYwLjIg4oCUINC60L7QvdCy0LXRgNGC0LDRhtC40Y8g0KbQldCb0J7Qk9CeINCw0YDRhdC40LLQsCAoWklQKSDQsiDQvtC00LjQvSDRhNC+0YDQvNCw0YIuCiMgZG9jeOKGknBkZiDQtNC10LvQsNC10YLRgdGPINCe0JTQndCY0Jwg0LLRi9C30L7QstC+0Lwgc29mZmljZSAo0LHQsNGC0YcpIOKAlCDQuNC90LDRh9C1INC90LAgfjE4INC00L7QutGD0LzQtdC90YLQsNGFCiMg0L/QvtGB0LvQtdC00L7QstCw0YLQtdC70YzQvdGL0LUg0LLRi9C30L7QstGLINGD0L/RgNGD0YLRgdGPINCyINGC0LDQudC80LDRg9GCINC30LDQv9GA0L7RgdCwLgojID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KCmRlZiBfYmF0Y2hfZG9jeF90b19wZGYobmFtZWRfZG9jeCwgdGltZW91dF9zZWM6IGludCA9IDE4MCkgLT4gZGljdDoKICAgICIiIlsobmFtZSwgZG9jeF9ieXRlcyksIC4uLl0g4oaSIHtuYW1lOiBwZGZfYnl0ZXN9LiDQntC00LjQvSDQstGL0LfQvtCyIHNvZmZpY2Ug0L3QsCDQstGB0LUuIiIiCiAgICBpZiBub3QgbmFtZWRfZG9jeDoKICAgICAgICByZXR1cm4ge30KICAgIHJlc3VsdCA9IHt9CiAgICB3aXRoIHRlbXBmaWxlLlRlbXBvcmFyeURpcmVjdG9yeShwcmVmaXg9InZrX3BrZ18iKSBhcyB0bXA6CiAgICAgICAgIyDRg9C90LjQutCw0LvRjNC90YvQtSDQsdC10LfQvtC/0LDRgdC90YvQtSDQuNC80LXQvdCwICjQuNC80LXQvdCwINCyIFpJUCDigJQg0LrQuNGA0LjQu9C70LjRhtCwL9C/0L7QstGC0L7RgNGLINC90LXQtNC+0L/Rg9GB0YLQuNC80Ysg0LTQu9GPIHNvZmZpY2UpCiAgICAgICAgbWFwcGluZyA9IFtdICAjIChuYW1lLCBzdGVtKQogICAgICAgIGZvciBpZHgsIChuYW1lLCBkYXRhKSBpbiBlbnVtZXJhdGUobmFtZWRfZG9jeCk6CiAgICAgICAgICAgIHN0ZW0gPSBmImR7aWR4OjAzZH0iCiAgICAgICAgICAgIHdpdGggb3Blbihvcy5wYXRoLmpvaW4odG1wLCBzdGVtICsgIi5kb2N4IiksICJ3YiIpIGFzIGY6CiAgICAgICAgICAgICAgICBmLndyaXRlKGRhdGEpCiAgICAgICAgICAgIG1hcHBpbmcuYXBwZW5kKChuYW1lLCBzdGVtKSkKICAgICAgICBjbWQgPSBbInNvZmZpY2UiLCAiLS1oZWFkbGVzcyIsICItLWNvbnZlcnQtdG8iLCAicGRmIiwgIi0tb3V0ZGlyIiwgdG1wXQogICAgICAgIGNtZCArPSBbb3MucGF0aC5qb2luKHRtcCwgc3RlbSArICIuZG9jeCIpIGZvciBfLCBzdGVtIGluIG1hcHBpbmddCiAgICAgICAgdHJ5OgogICAgICAgICAgICByID0gc3VicHJvY2Vzcy5ydW4oY21kLCBjYXB0dXJlX291dHB1dD1UcnVlLCB0aW1lb3V0PXRpbWVvdXRfc2VjKQogICAgICAgIGV4Y2VwdCBGaWxlTm90Rm91bmRFcnJvcjoKICAgICAgICAgICAgcmFpc2UgUnVudGltZUVycm9yKCJMaWJyZU9mZmljZSAoc29mZmljZSkg0L3QtSDQvdCw0LnQtNC10L0g0LIgUEFUSC4iKQogICAgICAgIGV4Y2VwdCBzdWJwcm9jZXNzLlRpbWVvdXRFeHBpcmVkOgogICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoZiJMaWJyZU9mZmljZSDQv9GA0LXQstGL0YHQuNC7IHt0aW1lb3V0X3NlY30g0YHQtdC6INC/0YDQuCDQsdCw0YLRhyBkb2N44oaScGRmLiIpCiAgICAgICAgaWYgci5yZXR1cm5jb2RlICE9IDA6CiAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcigiTGlicmVPZmZpY2Ug0LHQsNGC0YcgZG9jeOKGknBkZjogIiArIHIuc3RkZXJyLmRlY29kZSgidXRmLTgiLCAicmVwbGFjZSIpWzo1MDBdKQogICAgICAgIGZvciBuYW1lLCBzdGVtIGluIG1hcHBpbmc6CiAgICAgICAgICAgIHAgPSBvcy5wYXRoLmpvaW4odG1wLCBzdGVtICsgIi5wZGYiKQogICAgICAgICAgICBpZiBub3Qgb3MucGF0aC5leGlzdHMocCk6CiAgICAgICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoZiJQREYg0L3QtSDQv9C+0Y/QstC40LvRgdGPINC00LvRjyB7bmFtZX0gKNCx0LDRgtGHKS4iKQogICAgICAgICAgICB3aXRoIG9wZW4ocCwgInJiIikgYXMgZjoKICAgICAgICAgICAgICAgIHJlc3VsdFtuYW1lXSA9IGYucmVhZCgpCiAgICByZXR1cm4gcmVzdWx0CgoKZGVmIF93cml0ZV9wZGZfcGFnZXMoemYsIGZvbGRlcjogc3RyLCBsZWFmX2Jhc2U6IHN0ciwgcGRmX2J5dGVzOiBieXRlcywgZHBpOiBpbnQgPSAxNzAsIHF1YWxpdHk6IGludCA9IDg1KToKICAgICIiItCg0LDRgdGC0LXRgNC40LfRg9C10YIgUERGINC/0L7RgdGC0YDQsNC90LjRh9C90L4g0L/RgNGP0LzQviDQsiDQvtGC0LrRgNGL0YLRi9C5IFppcEZpbGU6IGZvbGRlci9sZWFmX2Jhc2Vf0YHRgtGATk4uanBnIiIiCiAgICBpbXBvcnQgZml0eiAgIyBQeU11UERGCiAgICB6b29tID0gZHBpIC8gNzIuMAogICAgbWF0ID0gZml0ei5NYXRyaXgoem9vbSwgem9vbSkKICAgIGRvYyA9IGZpdHoub3BlbihzdHJlYW09cGRmX2J5dGVzLCBmaWxldHlwZT0icGRmIikKICAgIHRyeToKICAgICAgICBuID0gZG9jLnBhZ2VfY291bnQKICAgICAgICBwYWQgPSBtYXgoMiwgbGVuKHN0cihuKSkpCiAgICAgICAgZm9yIGkgaW4gcmFuZ2Uobik6CiAgICAgICAgICAgIHBpeCA9IGRvYy5sb2FkX3BhZ2UoaSkuZ2V0X3BpeG1hcChtYXRyaXg9bWF0KQogICAgICAgICAgICBqcGcgPSBwaXgudG9ieXRlcygianBlZyIsIGpwZ19xdWFsaXR5PXF1YWxpdHkpCiAgICAgICAgICAgIHpmLndyaXRlc3RyKGYie2ZvbGRlcn17bGVhZl9iYXNlfV/RgdGC0YB7c3RyKGkgKyAxKS56ZmlsbChwYWQpfS5qcGciLCBqcGcpCiAgICBmaW5hbGx5OgogICAgICAgIGRvYy5jbG9zZSgpCgoKZGVmIGNvbnZlcnRfcGFja2FnZV96aXAoemlwX2J5dGVzOiBieXRlcywgdGFyZ2V0X2ZtdDogc3RyKSAtPiBieXRlczoKICAgICIiIgogICAg0J/QvtGB0YLQvtCx0YDQsNCx0L7RgtC60LAg0LPQvtGC0L7QstC+0LPQviBaSVAt0LDRgNGF0LjQstCwINC/0LDQutC10YLQsC4KICAgICAgbmF0aXZlICAgICAgICDihpIg0LrQsNC6INC10YHRgtGMCiAgICAgIHBkZiAgICAgICAgICAg4oaSIGRvY3jihpJQREYgKNCx0LDRgtGHIHNvZmZpY2UpOyBwZGYt0YTQvtGA0LzRiyDQvtGB0YLQsNGO0YLRgdGPIFBERgogICAgICBkb2N4IChXb3JkKSAgIOKGkiBkb2N4INC+0YHRgtCw0Y7RgtGB0Y87IHBkZi3RhNC+0YDQvNGLINC+0YHRgtCw0Y7RgtGB0Y8gUERGICjQvdC10YIgV29yZC3QuNGB0YXQvtC00L3QuNC60LApCiAgICAgIGpwZWcgICAgICAgICAg4oaSINC60LDQttC00YvQuSDQtNC+0LrRg9C80LXQvdGCIOKGkiDQv9C+0LTQv9Cw0L/QutCwINGB0L4g0YHRgtGA0LDQvdC40YbQsNC80Lgt0LrQsNGA0YLQuNC90LrQsNC80LgKICAgICIiIgogICAgdCA9ICh0YXJnZXRfZm10IG9yICIiKS5sb3dlcigpCiAgICBpZiB0IGluICgianBnIiwgImltYWdlIiwgImltYWdlcyIpOgogICAgICAgIHQgPSAianBlZyIKICAgIGlmIHQgaW4gKCIiLCAibmF0aXZlIik6CiAgICAgICAgcmV0dXJuIHppcF9ieXRlcwogICAgaWYgdCA9PSAiZG9jeCI6CiAgICAgICAgcmV0dXJuIHppcF9ieXRlcyAgIyBkb2N4INGD0LbQtSBkb2N4LCBwZGYt0YTQvtGA0LzRiyDQvdC1INC60L7QvdCy0LXRgNGC0LjRgNGD0Y7RgtGB0Y8g4oaSINCx0LXQtyDQuNC30LzQtdC90LXQvdC40LkKCiAgICB6aW4gPSB6aXBmaWxlLlppcEZpbGUoaW8uQnl0ZXNJTyh6aXBfYnl0ZXMpKQogICAgZW50cmllcyA9IFsoaS5maWxlbmFtZSwgemluLnJlYWQoaS5maWxlbmFtZSkpIGZvciBpIGluIHppbi5pbmZvbGlzdCgpIGlmIG5vdCBpLmZpbGVuYW1lLmVuZHN3aXRoKCIvIildCgogICAgIyBkb2N44oaScGRmINC+0LTQvdC40Lwg0LHQsNGC0YfQtdC8ICjQvdGD0LbQvdC+INC4INC00LvRjyBwZGYsINC4INC00LvRjyBqcGVnKQogICAgZG9jeF9uYW1lZCA9IFsobiwgZCkgZm9yIG4sIGQgaW4gZW50cmllcyBpZiBuLmxvd2VyKCkuZW5kc3dpdGgoIi5kb2N4IildCiAgICBwZGZfb2YgPSBfYmF0Y2hfZG9jeF90b19wZGYoZG9jeF9uYW1lZCkgaWYgZG9jeF9uYW1lZCBlbHNlIHt9CgogICAgb3V0ID0gaW8uQnl0ZXNJTygpCiAgICB3aXRoIHppcGZpbGUuWmlwRmlsZShvdXQsICJ3IiwgemlwZmlsZS5aSVBfREVGTEFURUQpIGFzIHpmOgogICAgICAgIGZvciBuYW1lLCBkYXRhIGluIGVudHJpZXM6CiAgICAgICAgICAgIGxvdyA9IG5hbWUubG93ZXIoKQogICAgICAgICAgICBiYXNlID0gbmFtZVs6LTVdIGlmIGxvdy5lbmRzd2l0aCgiLmRvY3giKSBlbHNlIChuYW1lWzotNF0gaWYgbG93LmVuZHN3aXRoKCIucGRmIikgZWxzZSBuYW1lKQogICAgICAgICAgICBsZWFmID0gYmFzZS5zcGxpdCgiLyIpWy0xXQogICAgICAgICAgICBpZiB0ID09ICJwZGYiOgogICAgICAgICAgICAgICAgaWYgbG93LmVuZHN3aXRoKCIuZG9jeCIpOgogICAgICAgICAgICAgICAgICAgIHpmLndyaXRlc3RyKGJhc2UgKyAiLnBkZiIsIHBkZl9vZltuYW1lXSkKICAgICAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICAgICAgemYud3JpdGVzdHIobmFtZSwgZGF0YSkKICAgICAgICAgICAgZWxpZiB0ID09ICJqcGVnIjoKICAgICAgICAgICAgICAgIGlmIGxvdy5lbmRzd2l0aCgiLmRvY3giKToKICAgICAgICAgICAgICAgICAgICBfd3JpdGVfcGRmX3BhZ2VzKHpmLCBiYXNlICsgIi8iLCBsZWFmLCBwZGZfb2ZbbmFtZV0pCiAgICAgICAgICAgICAgICBlbGlmIGxvdy5lbmRzd2l0aCgiLnBkZiIpOgogICAgICAgICAgICAgICAgICAgIF93cml0ZV9wZGZfcGFnZXMoemYsIGJhc2UgKyAiLyIsIGxlYWYsIGRhdGEpCiAgICAgICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgICAgIHpmLndyaXRlc3RyKG5hbWUsIGRhdGEpCiAgICByZXR1cm4gb3V0LmdldHZhbHVlKCkK"

def _p(rel): return os.path.join(ROOT, *rel.split("/"))

def update_doc_convert():
    path = _p("backend/app/services/doc_convert.py")
    data = base64.b64decode(DC_B64)
    if not os.path.exists(path):
        print("!!! doc_convert.py не найден — сначала Фаза 1."); sys.exit(1)
    if open(path, "rb").read() == data:
        print("[SKIP] doc_convert.py уже актуален (Pack 60.2)."); return
    with tempfile.NamedTemporaryFile("wb", suffix=".py", delete=False) as tf:
        tf.write(data); tmp = tf.name
    try: py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e: print("!!! doc_convert.py не компилируется:", e); sys.exit(3)
    finally: os.unlink(tmp)
    open(path + ".bak602", "wb").write(open(path, "rb").read())
    open(path, "wb").write(data)
    print("OK: doc_convert.py обновлён (.bak602).")

def patch_render_package():
    path = _p("backend/app/api/applications.py")
    raw = open(path, "rb").read(); crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")
    if "Pack 60.2" in norm: print("[SKIP] render_package уже пропатчен (Pack 60.2)."); return

    sig_old = (
        "async def render_package(  # Pack 57.0: def \u2192 async (\u0434\u043b\u044f await _ensure_...)\n"
        "    app_id: int,\n"
        "    session: Session = Depends(get_session),\n"
        "    user_id: int = Depends(current_user_id),\n"
        "):"
    )
    sig_new = (
        "async def render_package(  # Pack 57.0: def \u2192 async (\u0434\u043b\u044f await _ensure_...)\n"
        "    app_id: int,\n"
        '    format: str = Query("native", description="native|docx|pdf|jpeg"),  # Pack 60.2\n'
        "    session: Session = Depends(get_session),\n"
        "    user_id: int = Depends(current_user_id),\n"
        "):"
    )
    anchor = (
        "    _log_event(\n"
        '        session, app.id, "manager", user_id, "package_generated",'
    )
    block = (
        "    # Pack 60.2 \u2014 \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0430\u0446\u0438\u044f \u0432\u0441\u0435\u0433\u043e \u0430\u0440\u0445\u0438\u0432\u0430 \u0432 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 (native|docx|pdf|jpeg)\n"
        '    _pfmt = (format or "native").lower()\n'
        '    if _pfmt not in ("", "native"):\n'
        "        try:\n"
        "            from app.services.doc_convert import convert_package_zip\n"
        "            zip_bytes = convert_package_zip(zip_bytes, _pfmt)\n"
        "        except Exception as e:\n"
        "            import logging\n"
        '            logging.getLogger(__name__).exception("Pack 60.2: package format convert failed")\n'
        '            raise HTTPException(500, f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0430\u0440\u0445\u0438\u0432 \u0432 {_pfmt}: {type(e).__name__}: {e}")\n'
        "\n"
        "    _log_event(\n"
        '        session, app.id, "manager", user_id, "package_generated",'
    )
    for nm, a in (("sig", sig_old), ("anchor", anchor)):
        if norm.count(a) != 1:
            print(f"!!! \u044f\u043a\u043e\u0440\u044c {nm} = {norm.count(a)} (\u043d\u0443\u0436\u043d\u043e 1). \u0421\u0442\u043e\u043f."); sys.exit(2)
    new = norm.replace(sig_old, sig_new, 1).replace(anchor, block, 1)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(new); tmp = tf.name
    try: py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e: print("!!! applications.py не компилируется — не тронут:", e); os.unlink(tmp); sys.exit(3)
    os.unlink(tmp)
    open(path + ".bak602", "wb").write(raw)
    open(path, "wb").write((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print("OK: render_package пропатчен (.bak602). CRLF:", crlf)

if __name__ == "__main__":
    update_doc_convert(); patch_render_package()
    print("\nГотово (бэкенд Фазы 3). docx→pdf батчем — один вызов soffice на весь архив.")
