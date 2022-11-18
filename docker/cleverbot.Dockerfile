FROM python:3.10-bullseye
WORKDIR /app
COPY ./ /app
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    playwright install
CMD [ "python", "cleverbot.py"]