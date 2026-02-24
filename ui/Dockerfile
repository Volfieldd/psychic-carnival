FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ENV VITE_API_URL=http://localhost:8000
CMD ["npm", "run", "dev"]
