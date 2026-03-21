import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image
import os
import random
import logging

logger = logging.getLogger(__name__)

class ChartCNN(nn.Module):
    """
    서동진님의 '비슷한 그래프 찾기' 직관을 구현하는
    주식 차트 패턴 인식용 Convolutional Neural Network (CNN).
    """
    def __init__(self, num_classes=2): # Buy(급등), Hold(유지) 2개 클래스
        super(ChartCNN, self).__init__()

        # 1. 특징 추출부 (Convolutional Layers)
        # 이미지의 선, 면, 캔들 꼬리 등의 특징을 학습
        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)

        # 2. 결정부 (Fully Connected Layers)
        # 추출된 특징을 바탕으로 '매수' 확률을 계산
        self.fc1 = nn.Linear(128 * 8 * 8, 512) # 64x64 이미지가 풀링을 거쳐 8x8로 축소됨
        self.fc2 = nn.Linear(512, num_classes)
        self.dropout = nn.Dropout(0.3)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x))) # 특징 1
        x = self.pool(F.relu(self.conv2(x))) # 특징 2
        x = self.pool(F.relu(self.conv3(x))) # 특징 3

        x = x.view(-1, 128 * 8 * 8) # 벡터화
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        return x

class VisionEngine:
    def __init__(self, model_path=None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = ChartCNN().to(self.device)
        self._model_loaded = False

        if model_path and os.path.exists(model_path):
            self.model.load_state_dict(torch.load(model_path, map_location=self.device))
            self._model_loaded = True
            print(f"학습된 AI 모델 로드 완료: {model_path}")

        self.model.eval()

        # 이미지 전처리 설정 (64x64 리사이즈, 텐서 변환)
        self.transform = transforms.Compose([
            transforms.Resize((64, 64)),
            transforms.ToTensor(),
            transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
        ])

    @property
    def is_trained(self) -> bool:
        """실제 모델이 로드되었으면 True, 아니면 False"""
        return self._model_loaded

    def predict(self, image_path):
        """저장된 차트 이미지를 보고 매수 추천 확률을 반환합니다."""
        if not self._model_loaded:
            logger.warning("⚠️ 학습된 모델 없음 — 랜덤 예측 모드로 동작 중")
            return random.uniform(0, 100)

        image = Image.open(image_path).convert('RGB')
        image = self.transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            outputs = self.model(image)
            # Softmax를 통해 확률값 계산 (0~1 사이)
            probabilities = F.softmax(outputs, dim=1)
            buy_prob = probabilities[0][0].item() * 100 # 매수 확률 (%)

        return buy_prob

if __name__ == "__main__":
    # 간단한 작동 테스트
    engine = VisionEngine()
    print("AI Vision Engine 초기화 완료 (테스트 모드)")
    print(f"모델 학습 여부: {engine.is_trained}")
