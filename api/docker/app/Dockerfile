FROM python:3.12

# 业务运行时保持 UTC，展示层按租户配置转换。
ENV TZ=UTC
ENV PATH=/usr/local/lib/python3.12/site-packages:$PATH
RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app

COPY requirements.txt /usr/src/app/
RUN pip install ipython
RUN pip install --no-cache-dir -r requirements.txt

COPY .. .
