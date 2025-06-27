export PYTHONPATH="${PYTHONPATH}:/home/zhushengmao/asn/"
CUDA_VISIBLE_DEVICES=6 vllm serve /data1/zhushengmao/Qwen2___5-14B-Instruct --port 8001 --gpu-memory-utilization 0.7 --max-model-len 16384
CUDA_VISIBLE_DEVICES=7 vllm serve /data1/zhushengmao/gte_Qwen2-7B-instruct --port 8002 --task embedding --gpu-memory-utilization 0.5 --max-model-len 32768