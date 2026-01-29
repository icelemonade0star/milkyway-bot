import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sshtunnel import SSHTunnelForwarder

load_dotenv()

# SSH 터널 설정 (기존 코드 그대로)
server = SSHTunnelForwarder(
    (os.getenv("SSH_HOST"), int(os.getenv("SSH_PORT"))),
    ssh_username=os.getenv("SSH_USER"),
    ssh_password=os.getenv("SSH_PASSWORD"),
    remote_bind_address=(os.getenv("DB_HOST"), int(os.getenv("DB_PORT")))
)

server.start()
print("✅ SSH 터널 연결됨")
print(f"로컬 포트: {server.local_bind_port}")

try:
    # SQLAlchemy 엔진 생성 (localhost + 터널 포트 사용)
    DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:{server.local_bind_port}/{os.getenv('DB_NAME')}"
    
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    # 세션 사용
    with SessionLocal() as session:
        # 1. Raw SQL 쿼리
        result = session.execute(text("SELECT version()"))
        print("PostgreSQL 버전:", result.scalar())
        
        # 2. 테이블 조회 (예시)
        result = session.execute(text("" \
        "SELECT * FROM auth_token LIMIT 5"
        ""))
        for row in result:
            print(row)
            
        # 3. ORM 모델 사용 예시
        # User.query.filter(User.id == 1).first()
        
finally:
    server.stop()
    print("🔒 SSH 터널 종료")