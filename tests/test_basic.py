import unittest

from staticflow import Cell, Flow


class TestCell(unittest.TestCase):
    def test_cell(self):
        cell = Cell('''\
a = b + 1
c = 4
del d
e = 1
def f(g):
    h = i + 6
del c
''')
        self.assertEqual(cell.reads, set('bdi'))
        self.assertEqual(cell.writes, set('adef'))


class TestFlow(unittest.TestCase):
    def test_mock(self):
        TODO  # Mock Cell and test Flow methods

    def test_complete(self):
        TODO  # Test on a simple list of cells
