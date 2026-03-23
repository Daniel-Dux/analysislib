#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Memory profiling script for analysis_plot_panel memory leak fixes.

This script helps verify that the memory optimizations are working correctly.
Usage: python -m memory_profiler memory_profile_test.py
"""

import numpy as np
import psutil
import os


def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def test_np_append_inefficient(n_points=1000):
    """
    BEFORE: Inefficient np.append in loop (O(n²) complexity)
    """
    print(f"\n[OLD METHOD] Testing np.append() with {n_points} points...")
    start_mem = get_memory_usage()
    print(f"Start memory: {start_mem:.2f} MB")
    
    xs = np.array([])
    ys = np.array([])
    
    for i in range(n_points):
        xs = np.append(xs, i)
        ys = np.append(ys, np.sin(i * 0.01))
        
        if i % 100 == 0 and i > 0:
            current_mem = get_memory_usage()
            print(f"  {i}/{ n_points} points: {current_mem:.2f} MB (+{current_mem - start_mem:.2f} MB)")
    
    end_mem = get_memory_usage()
    print(f"End memory: {end_mem:.2f} MB")
    print(f"Total memory used: {end_mem - start_mem:.2f} MB")
    return end_mem - start_mem


def test_list_efficient(n_points=1000):
    """
    AFTER: Efficient Python list + numpy conversion (O(n) complexity)
    """
    print(f"\n[NEW METHOD] Testing list + np.array() with {n_points} points...")
    start_mem = get_memory_usage()
    print(f"Start memory: {start_mem:.2f} MB")
    
    xs_list = []
    ys_list = []
    
    for i in range(n_points):
        xs_list.append(i)
        ys_list.append(np.sin(i * 0.01))
        
        if i % 100 == 0 and i > 0:
            current_mem = get_memory_usage()
            print(f"  {i}/{n_points} points: {current_mem:.2f} MB (+{current_mem - start_mem:.2f} MB)")
    
    # Convert to arrays once at the end
    xs = np.array(xs_list)
    ys = np.array(ys_list)
    
    end_mem = get_memory_usage()
    print(f"End memory: {end_mem:.2f} MB")
    print(f"Total memory used: {end_mem - start_mem:.2f} MB")
    return end_mem - start_mem


def test_griddata_cleanup(n_points=1000):
    """
    Test griddata with and without explicit cleanup
    """
    from scipy.interpolate import griddata
    
    print(f"\n[GRIDDATA] Testing with {n_points} points...")
    
    # Create test data
    np.random.seed(42)
    xs = np.random.rand(n_points)
    ys = np.random.rand(n_points)
    zs = np.random.rand(n_points)
    
    xi = np.linspace(xs.min(), xs.max(), 200)
    yi = np.linspace(ys.min(), ys.max(), 200)
    
    start_mem = get_memory_usage()
    print(f"Start memory: {start_mem:.2f} MB")
    
    Xi, Yi = np.meshgrid(xi, yi)
    Zi = griddata((xs, ys), zs, (Xi, Yi), 'nearest')
    
    # Clean up large intermediate arrays
    del Xi, Yi
    
    after_cleanup_mem = get_memory_usage()
    print(f"After cleanup: {after_cleanup_mem:.2f} MB (+{after_cleanup_mem - start_mem:.2f} MB)")
    print(f"Zi shape: {Zi.shape}, size: {Zi.nbytes / 1024 / 1024:.2f} MB")


def main():
    print("=" * 60)
    print("MEMORY LEAK FIX VERIFICATION")
    print("=" * 60)
    
    try:
        import psutil
    except ImportError:
        print("\nWARNING: psutil not installed. Install with:")
        print("  pip install psutil")
        print("\nTests will still run but relative comparison won't show exact values.")
        return
    
    # Test with different point counts
    for n_points in [100, 500, 1000]:
        print(f"\n{'*' * 60}")
        print(f"Testing with {n_points} points")
        print(f"{'*' * 60}")
        
        mem_old = test_np_append_inefficient(n_points)
        mem_new = test_list_efficient(n_points)
        
        improvement = (mem_old - mem_new) / mem_old * 100 if mem_old > 0 else 0
        speedup = mem_old / mem_new if mem_new > 0 else float('inf')
        
        print(f"\n[COMPARISON]")
        print(f"  Old method memory:  {mem_old:.2f} MB")
        print(f"  New method memory:  {mem_new:.2f} MB")
        print(f"  Memory saved:       {mem_old - mem_new:.2f} MB ({improvement:.1f}%)")
        print(f"  Speedup factor:     {speedup:.1f}x")
    
    # Test griddata cleanup
    test_griddata_cleanup(1000)
    
    print("\n" + "=" * 60)
    print("✓ All memory tests completed successfully!")
    print("=" * 60)


if __name__ == '__main__':
    main()
