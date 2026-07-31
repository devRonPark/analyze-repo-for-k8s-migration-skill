# ADR-2026-07-30-007: Summary 출력 형식은 E2E로 결정한다

- 상태: 채택됨
- 날짜: 2026-07-30
- 관련 작업: JPetStore 6 Summary E2E, [ADR-2026-07-30-004-deterministic-summary-delivery.md](ADR-2026-07-30-004-deterministic-summary-delivery.md)

## 관찰 결과

JPetStore 6 Summary E2E에서 Qwen3.6-35B-A3B는 필요한 저장소 근거를 수집했지만,
Markdown table을 포함한 보고서는 최종 응답을 끝내지 못했다.

2절만 bullet로 바꾸고 3·4절 table을 유지한 variant도 완료되지 않았다. 반면 Summary
전체를 간결한 bullet로 바꾼 variant는 5개 섹션의 최종 보고서를 1분 11초에 완료했다.
두 실행 모두 JPetStore 대상 저장소를 변경하지 않았다.

이 E2E 조건에서는 이 모델이 Markdown table보다 bullet 출력 형식을 더 빠르고
완결성 있게 처리했다. 이는 모델 일반의 table 생성 불가능을 뜻하지 않으며, 현재
provider·prompt·출력 예산 조합에서 확인된 관찰이다.

## 결정

1. Summary는 자유형 Markdown table 대신 대상·관계·열린 항목을 간결한 bullet로
   출력한다. 필드와 한국어 사용자 표시값은 유지한다.
2. 출력 형식 변경은 추측이 아니라 실험으로 판단한다. 같은 대상, provider, prompt,
   timeout에서 완료율·계약 유효성·golden-set 점수를 비교한다.
3. table을 피하려는 이유만으로 JSON 추출 파이프라인을 추가하지 않는다. bullet
   variant도 완료율이나 사실 정확도가 부족할 때만 재검토한다.

## 재발 방지

- template, renderer, validator, fixture는 같은 bullet 계약을 사용한다. prompt나
  template만 바꾼 실험은 유효하지 않다.
- 최종 보고서가 완료되지 않으면 tool read나 부분 본문에 golden-set 부분 점수를
  주지 않는다.
- 모델 출력 형식의 한계를 주장하려면 재현 가능한 A/B E2E 결과를 남긴다.
