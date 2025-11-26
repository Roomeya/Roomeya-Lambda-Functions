# Roomeya Lambda Functions

Roomeya 프로젝트의 AWS Lambda 함수 소스 코드를 관리하는 레포지토리입니다.

## 📦 Lambda 함수 목록

### 폼 관리
- **CreateForm**: 새로운 폼 생성
- **getFormList**: 폼 목록 조회
- **SubmitForm**: 폼 제출 처리

### 파일 & 데이터 처리
- **upload-url**: S3 업로드 URL 생성
- **excelProcessor**: 엑셀 파일 처리
- **identify_student**: 학생 식별

### 매칭 시스템
- **matchingProcessor**: 학생 매칭 처리
- **matchingResult**: 매칭 결과 조회

### 알림
- **emailSender**: SES를 통한 이메일 발송

## 🏗️ 디렉토리 구조

```
roomeya-lambda-functions/
├── README.md
├── CreateForm/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── getFormList/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── SubmitForm/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── upload-url/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── excelProcessor/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── identify_student/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── matchingProcessor/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── matchingResult/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── emailSender/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
├── scripts/
│   ├── build.sh          # 전체 빌드 스크립트
│   ├── deploy.sh         # 배포 스크립트
│   └── test.sh           # 테스트 스크립트
└── .github/
    └── workflows/
        └── deploy.yml    # CI/CD 파이프라인
```

## 🚀 개발 가이드

### 로컬 개발 환경 설정

```bash
# Python 가상환경 생성
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치 (각 함수별)
cd getFormList
pip install -r requirements.txt
```

### 함수 테스트

```bash
# 단일 함수 테스트
cd getFormList
python -m pytest tests/

# 전체 함수 테스트
./scripts/test.sh
```

### 로컬에서 Lambda 실행 (SAM 사용)

```bash
# SAM CLI 설치
brew install aws-sam-cli

# 로컬 실행
sam local invoke getFormList -e events/test-event.json
```

## 📦 빌드 & 배포

### 빌드 스크립트

각 함수를 zip 파일로 패키징:

```bash
./scripts/build.sh
```

생성된 파일:
```
dist/
├── CreateForm.zip
├── getFormList.zip
├── SubmitForm.zip
├── upload-url.zip
├── excelProcessor.zip
├── identify_student.zip
├── matchingProcessor.zip
├── matchingResult.zip
└── emailSender.zip
```

### 수동 배포

```bash
# S3에 업로드
aws s3 cp dist/getFormList.zip s3://roomeya-lambda-deployments/

# Lambda 함수 업데이트
aws lambda update-function-code \
  --function-name getFormList \
  --s3-bucket roomeya-lambda-deployments \
  --s3-key getFormList.zip
```

### Terraform 연동 배포

```bash
# 1. Lambda 코드 빌드
./scripts/build.sh

# 2. Infrastructure 레포로 이동
cd ../roomeya-infrastructure

# 3. Terraform 적용
terraform apply
```

## 🔄 CI/CD 파이프라인

GitHub Actions를 통한 자동 배포:

```yaml
# .github/workflows/deploy.yml
name: Deploy Lambda Functions

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.14'
      - name: Build
        run: ./scripts/build.sh
      - name: Deploy to S3
        run: |
          aws s3 sync dist/ s3://roomeya-lambda-deployments/
      - name: Update Lambda Functions
        run: ./scripts/deploy.sh
```

## 🧪 테스트

### 단위 테스트

```python
# tests/test_lambda_function.py
import pytest
from lambda_function import lambda_handler

def test_lambda_handler():
    event = {"formId": "test-123"}
    context = {}
    
    response = lambda_handler(event, context)
    
    assert response['statusCode'] == 200
```

### 통합 테스트

```bash
# AWS 환경에서 실제 테스트
./scripts/integration-test.sh
```

## 📋 공통 의존성

모든 Lambda 함수가 사용하는 공통 라이브러리:

```txt
# requirements.txt
boto3>=1.28.0
```

## 🔗 관련 레포지토리

- **Infrastructure**: [roomeya-infrastructure](../roomeya-infrastructure) - Terraform 인프라 코드

## 🛠️ 개발 규칙

### 코드 스타일
- PEP 8 준수
- Type hints 사용
- Docstring 작성

### 에러 처리
```python
def lambda_handler(event, context):
    try:
        # 로직
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

### 환경 변수
```python
import os

TABLE_NAME = os.environ.get('TABLE_NAME', 'Roomeya-Forms')
```

## ⚠️ 주의사항

- **Python 버전**: 3.14 사용
- **패키지 크기**: Lambda 제한 (250MB unzipped) 주의
- **타임아웃**: 각 함수별 적절한 timeout 설정
- **메모리**: 최소 128MB, 필요시 증가
- **환경 변수**: 민감 정보는 AWS Secrets Manager 사용

## 📝 라이센스

MIT License
