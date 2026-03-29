# Example Configurations

## Example 1: Geospatial Foundation Models for Agriculture

```yaml
project:
  name: "GFM Agricultural Change Detection Review"

search:
  date_range: {start: "2015-01-01", end: "2026-03-29"}
  sources: [arxiv, openalex, semantic_scholar]
  queries:
    - name: "gfm_embeddings"
      terms: >
        ("geospatial foundation model" OR "remote sensing foundation model")
        AND ("embedding" OR "self-supervised" OR "pre-trained")
    - name: "crop_change"
      terms: >
        ("crop change detection" OR "cropland abandonment")
        AND ("deep learning" OR "foundation model")
        AND ("remote sensing" OR "satellite")

screening:
  rules:
    include_keywords: [foundation model, remote sensing, crop, agriculture, embedding, change detection]
    exclude_keywords: [medical imaging, clinical, genomics]
    min_include_hits: 2
```

## Example 2: AI in Healthcare

```yaml
project:
  name: "AI Diagnostic Tools Systematic Review"

search:
  date_range: {start: "2018-01-01", end: "2026-03-29"}
  sources: [openalex, semantic_scholar]
  queries:
    - name: "ai_diagnosis"
      terms: >
        ("artificial intelligence" OR "deep learning" OR "machine learning")
        AND ("diagnosis" OR "diagnostic" OR "detection")
        AND ("medical imaging" OR "radiology" OR "pathology")

screening:
  rules:
    include_keywords: [deep learning, diagnosis, medical imaging, radiology, CNN, transformer]
    exclude_keywords: [agriculture, remote sensing, autonomous driving, robotics]
    min_include_hits: 2
```

## Example 3: Climate Change and ML

```yaml
project:
  name: "ML for Climate Change Prediction Review"

search:
  date_range: {start: "2015-01-01", end: "2026-03-29"}
  sources: [arxiv, openalex, semantic_scholar]
  queries:
    - name: "climate_ml"
      terms: >
        ("climate change" OR "global warming" OR "climate prediction")
        AND ("machine learning" OR "deep learning" OR "neural network")
    - name: "weather_forecast"
      terms: >
        ("weather forecasting" OR "climate modeling")
        AND ("transformer" OR "foundation model" OR "graph neural network")

screening:
  rules:
    include_keywords: [climate, weather, prediction, deep learning, neural network, forecast]
    exclude_keywords: [medical, drug, protein, genomics]
    min_include_hits: 2
```

## Example 4: Software Engineering

```yaml
project:
  name: "LLMs for Code Generation Review"

search:
  date_range: {start: "2020-01-01", end: "2026-03-29"}
  sources: [arxiv, semantic_scholar]
  queries:
    - name: "llm_code"
      terms: >
        ("large language model" OR "code generation" OR "code completion")
        AND ("software engineering" OR "programming" OR "developer")

screening:
  rules:
    include_keywords: [code generation, LLM, software engineering, programming, code completion]
    exclude_keywords: [medical, biology, chemistry, remote sensing]
    min_include_hits: 2
```
