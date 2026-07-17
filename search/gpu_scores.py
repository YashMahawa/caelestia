#!/usr/bin/python3
"""Compute cosine dot products on the Intel iGPU over a binary stdin payload."""

import sys

import numpy as np
import pyopencl as cl

rows = int(sys.argv[1])
dimensions = int(sys.argv[2])
payload = sys.stdin.buffer.read()
expected = (dimensions + rows * dimensions) * 4
if len(payload) != expected:
    raise SystemExit(f"invalid payload: {len(payload)} != {expected}")

values = np.frombuffer(payload, dtype=np.float32)
query = values[:dimensions]
matrix = values[dimensions:].reshape(rows, dimensions)

device = next(
    device
    for platform in cl.get_platforms()
    for device in platform.get_devices(device_type=cl.device_type.GPU)
    if "Intel" in device.vendor or "Intel" in device.name
)
context = cl.Context([device])
queue = cl.CommandQueue(context)
program = cl.Program(context, """
__kernel void cosine_scores(
    __global const float *matrix,
    __global const float *query,
    __global float *scores,
    const int dimensions)
{
    int row = get_global_id(0);
    float total = 0.0f;
    int base = row * dimensions;
    for (int column = 0; column < dimensions; ++column)
        total += matrix[base + column] * query[column];
    scores[row] = total;
}
""").build(options=["-cl-fast-relaxed-math"])

flags = cl.mem_flags
matrix_buffer = cl.Buffer(context, flags.READ_ONLY | flags.COPY_HOST_PTR, hostbuf=matrix)
query_buffer = cl.Buffer(context, flags.READ_ONLY | flags.COPY_HOST_PTR, hostbuf=query)
scores = np.empty(rows, dtype=np.float32)
scores_buffer = cl.Buffer(context, flags.WRITE_ONLY, scores.nbytes)
program.cosine_scores(queue, (rows,), None, matrix_buffer, query_buffer, scores_buffer, np.int32(dimensions))
cl.enqueue_copy(queue, scores, scores_buffer).wait()
sys.stdout.buffer.write(scores.tobytes())
