# BP SSE Subscription API

혈압 측정 완료 결과를 클라이언트가 단방향 실시간으로 받기 위한 SSE(Server-Sent Events) 구독 API입니다.

## Endpoint

```http
GET /api/v1/biosignal/bp/{patient_id}/sse
```

예시:

```http
GET /api/v1/biosignal/bp/a5d6b9cf-5f76-46f3-bc07-f393af8d4294/sse
```

## Headers

```http
Authorization: Bearer <accessToken>
Accept: text/event-stream
```

`accessToken`은 query string으로 보내지 않습니다. 반드시 `Authorization` header의 Bearer token으로 전달합니다.

## Authentication

토큰 권한별 구독 조건은 다음과 같습니다.

| 권한 | 구독 가능 범위 |
| --- | --- |
| `patient` | 본인 `patient_id`만 구독 가능 |
| `practitioner` | 서버의 환자 접근 권한 검사를 통과한 환자만 구독 가능 |
| `administrator` | 모든 환자 구독 가능 |

권한이 없거나 토큰이 없으면 `401` 또는 `403` 응답이 반환됩니다.

## Event Format

연결 직후 서버는 연결 확인용 comment를 보냅니다.

```text
: connected
```

15초 동안 혈압 이벤트가 없으면 연결 유지를 위해 keep-alive comment를 보냅니다.

```text
: keep-alive
```

혈압 측정 결과가 발생하면 `bp.updated` 이벤트가 전달됩니다.

```text
id: 1710000000000
event: bp.updated
data: {"type":"bp.updated","patient_id":"a5d6b9cf-5f76-46f3-bc07-f393af8d4294","timestamp":1710000000000,"base_sbp":120,"base_dbp":80,"predicted_sbp":123.4,"predicted_dbp":82.1,"started_at":1709999970000,"ended_at":1710000000000}
```

## Data Payload

`data`는 JSON 문자열입니다.

```json
{
  "type": "bp.updated",
  "patient_id": "a5d6b9cf-5f76-46f3-bc07-f393af8d4294",
  "timestamp": 1710000000000,
  "base_sbp": 120,
  "base_dbp": 80,
  "predicted_sbp": 123.4,
  "predicted_dbp": 82.1,
  "started_at": 1709999970000,
  "ended_at": 1710000000000
}
```

| Field | Type | Description |
| --- | --- | --- |
| `type` | string | 이벤트 타입. 항상 `bp.updated` |
| `patient_id` | string | 환자 UUID |
| `timestamp` | number | 이벤트 기록 시각, Unix timestamp milliseconds |
| `base_sbp` | number | 기준 수축기 혈압 |
| `base_dbp` | number | 기준 이완기 혈압 |
| `predicted_sbp` | number | 최종 측정 수축기 혈압 |
| `predicted_dbp` | number | 최종 측정 이완기 혈압 |
| `started_at` | number | 분석 구간 시작 시각, Unix timestamp milliseconds |
| `ended_at` | number | 분석 구간 종료 시각, Unix timestamp milliseconds |

## Client Example

브라우저 기본 `EventSource`는 `Authorization` header를 직접 설정할 수 없습니다. 현재 API는 Bearer header 인증을 사용하므로 fetch 기반 SSE client를 사용해야 합니다.

예시: `@microsoft/fetch-event-source`

```ts
import { fetchEventSource } from "@microsoft/fetch-event-source";

const patientId = "a5d6b9cf-5f76-46f3-bc07-f393af8d4294";

await fetchEventSource(`/api/v1/biosignal/bp/${patientId}/sse`, {
  headers: {
    Authorization: `Bearer ${accessToken}`,
    Accept: "text/event-stream",
  },
  onmessage(event) {
    if (event.event !== "bp.updated") {
      return;
    }

    const bp = JSON.parse(event.data);
    console.log(bp.predicted_sbp, bp.predicted_dbp);
  },
  onerror(error) {
    console.error("BP SSE error", error);
    throw error;
  },
});
```

## curl Test

```bash
curl -N \
  -H "Authorization: Bearer <accessToken>" \
  -H "Accept: text/event-stream" \
  "http://localhost/api/v1/biosignal/bp/a5d6b9cf-5f76-46f3-bc07-f393af8d4294/sse"
```

## Notes

- 이 SSE는 연결 이후 새로 발생하는 혈압 측정 결과만 전달합니다.
- 과거 혈압 측정 결과 조회는 기존 `GET /api/v1/biosignal/bp/{patient_id}` API를 사용합니다.
- 서버는 Kafka의 `biosignal.BP.measured` 이벤트를 받아 `bp.updated` SSE 이벤트로 변환합니다.
- BP 측정 이벤트의 `ended_at`이 서버 현재 시각과 크게 어긋나면 실시간 이벤트로 전달되지 않을 수 있습니다.
