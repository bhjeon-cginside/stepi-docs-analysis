```json
{
  "run_id": "run-20260702T220428-e494b7a92562",
  "category": "quality_report",
  "classification_reason": "허용 범주와 일치하지 않는 정책 브리프 문서로 보여 임시로 성적서에 낮은 신뢰도로 분류",
  "region_count": 3,
  "active_region_source": "vlm_fallback",
  "caveat": "현재 domain pack은 STEPI용이 아니므로 extraction 품질 비교가 아니라 orchestration/detection proof로만 사용",
  "regions": [
    {
      "region_id": "p001_vf001",
      "label": "text",
      "bbox": [
        127,
        356,
        770,
        438
      ],
      "score": 0.95
    },
    {
      "region_id": "p001_vf002",
      "label": "text",
      "bbox": [
        94,
        477,
        806,
        648
      ],
      "score": 0.93
    },
    {
      "region_id": "p001_vf003",
      "label": "text",
      "bbox": [
        86,
        689,
        814,
        1161
      ],
      "score": 0.96
    }
  ]
}
```
