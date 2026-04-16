FROM nginx:alpine

# Copy static files
COPY index.html /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/

# Copy Python backend (optional, for API endpoints)
COPY requirements.txt /app/
COPY modules/ /app/modules/
COPY utils/ /app/utils/
COPY config.py /app/

# Install Python for backend API
RUN apk add --no-cache python3 py3-pip
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Expose port
ENV PORT=80
EXPOSE 80

# Health check
HEALTHCHECK CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
