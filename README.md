# Ubuntu System Monitor

Ubuntu/GNOME에 맞춘 간단한 실시간 시스템 모니터 GUI입니다.

## 기능

- CPU 사용량 그래프: 전체 / 코어별 선택
- 메모리 사용량 그래프
- CPU 온도 그래프: 평균 / 센서별 선택
- NVMe SSD 온도 그래프: 평균 / 장치 센서별 선택
- 스토리지 용량 도넛 그래프
- 1초마다 업데이트
- 기록 길이: 1분, 3분, 5분, 10분, 30분 선택

## 실행

```bash
ubuntu-system-monitor
```

또는:

```bash
/home/beom/.local/bin/ubuntu-system-monitor
```

## 설치 파일

- 앱 경로: `/home/beom/.openclaw/workspace/ubuntu-system-monitor`
- 실행 런처: `/home/beom/.local/bin/ubuntu-system-monitor`
- Desktop entry: `/home/beom/.local/share/applications/ubuntu-system-monitor.desktop`

## 참고

온도 센서는 가능한 한 sudo 없이 `/sys/class/hwmon`, `/sys/class/nvme` 기반으로 읽습니다. 하드웨어에 따라 일부 센서가 표시되지 않을 수 있습니다.
