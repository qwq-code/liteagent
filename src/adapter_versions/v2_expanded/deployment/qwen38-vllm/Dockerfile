FROM local/vllm-qwen35:26.07-xgrammar-0.2.4

# Qwen3.8's multimodal processor is authored against Transformers 5.8. Keep
# the proven NVIDIA/vLLM base and isolate this dependency change from Qwen3.5.
RUN python -m pip install --no-cache-dir "transformers==5.8.0" \
    && python -c "import transformers, vllm, xgrammar; assert transformers.__version__ == '5.8.0'; assert hasattr(xgrammar, 'normalize_tool_choice'); print(vllm.__version__)"
