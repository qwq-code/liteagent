FROM nvcr.io/nvidia/vllm:26.07-py3

# NVIDIA 26.07 pins xgrammar 0.2.0, but this vLLM build imports
# normalize_tool_choice, which first appears in later xgrammar releases.
# Keep every other image dependency pinned and replace xgrammar only.
RUN python -m pip install --no-cache-dir --no-deps xgrammar==0.2.4 \
    && python -c "import importlib.metadata as m, transformers, xgrammar; assert transformers.__version__ == '5.6.1'; assert hasattr(xgrammar, 'normalize_tool_choice'); print(m.version('xgrammar'))"
