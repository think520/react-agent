"""Tests for rag.query_router — rule-based routing."""

import pytest
from rag.query_router import auto_route


class TestAutoRoute:
    def test_default_hybrid(self):
        assert auto_route("什么是神经网络") == "hybrid"
        assert auto_route("explain gradient descent") == "hybrid"
        assert auto_route("") == "hybrid"

    def test_directory_grep_patterns(self):
        assert auto_route("在哪里提到ReLU") == "directory_grep"
        assert auto_route("哪里提到过激活函数") == "directory_grep"
        assert auto_route("原文怎么说的") == "directory_grep"
        assert auto_route("这个概念的出处是什么") == "directory_grep"
        assert auto_route("引用原文") == "directory_grep"
        assert auto_route("包含这个词的上下文") == "directory_grep"

    def test_directory_patterns(self):
        assert auto_route("哪些文档讲了反向传播") == "directory"
        assert auto_route("应该看哪些资料") == "directory"
        assert auto_route("文档列表") == "directory"
        assert auto_route("哪一章讲了CNN") == "directory"

    def test_priority_grep_over_directory(self):
        # "原文" triggers directory_grep before directory
        assert auto_route("原文出处是哪些文档") == "directory_grep"

    def test_english_patterns(self):
        assert auto_route("where is ReLU mentioned") == "directory_grep"
        assert auto_route("which documents cover CNN") == "directory"

    def test_whitespace_handling(self):
        assert auto_route("  什么是梯度  ") == "hybrid"
        assert auto_route("  在哪里提到  ") == "directory_grep"
