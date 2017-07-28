import ast
import logging
import sys


logger = logging.getLogger('staticflow')


PY3 = sys.version_info[0] == 3


if PY3:
    irange = range
    itervalues = lambda d: d.values()
    int_types = int,
    unicode_ = str
    text = str
else:
    irange = xrange  # noqa: F821
    itervalues = lambda d: d.itervalues()
    int_types = int, long  # noqa: F821
    unicode_ = unicode  # noqa: F821
    text = str, unicode_


def default(dct, key, cstr):
    try:
        return dct[key]
    except KeyError:
        value = cstr()
        dct[key] = value
        return value


class Scope(object):
    def __init__(self):
        self.globals = set()
        self.locals = set()


class _CellVisitor(ast.NodeVisitor):
    def __init__(self, cell):
        self.cell = cell
        self.scopes = []

    @property
    def in_global_scope(self):
        return not self.scopes

    def visit(self, node):
        """Overridden version of visit that can take a list of nodes.
        """
        if isinstance(node, list):
            for n in node:
                self.visit(n)
        else:
            ast.NodeVisitor.visit(self, node)

    def local_scope_visit(self, node):
        """Visit a node that creates a local scope.

        The nodes encountered down here do not assign to the global scope.
        """
        self.scopes.append(Scope())
        logger.debug("Entered local scope (%d)", len(self.scopes))
        try:
            self.visit(node)
        finally:
            self.scopes.pop()
            logger.debug("Left local scope (%d)", len(self.scopes))

    def assign(self, symbol):
        logger.debug("Assigning %r", symbol)
        if isinstance(symbol, ast.Name):
            symbol = symbol.id
        if isinstance(symbol, text):
            if self.in_global_scope or symbol in self.scopes[-1].globals:
                logger.debug("Added to writes: %r", symbol)
                self.cell.writes.add(symbol)
            else:
                logger.debug("In local context")
                self.scopes[-1].locals.add(symbol)
        elif isinstance(symbol, ast.Subscript):
            self.visit(symbol.slice)
            self.assign(symbol.value)
        elif isinstance(symbol, ast.Attribute):
            self.assign(symbol.value)

    # Handlers for specific node types

    def visit_FunctionDef(self, node):
        """Function definition (def keyword).

        Create a symbol in the current scope for the function, and handle the
        body (which is its own local scope).

        Note that default values for the arguments might access variables.
        """
        self.assign(node.name)
        self.visit(node.args.defaults)
        self.visit(node.decorator_list)
        self.local_scope_visit(node.body)

    def visit_ClassDef(self, node):
        """Class definition (class keyword).

        Create a symbol in the current scope for the class, and handle the body
        (which is its own local scope).
        """
        self.assign(node.name)
        self.visit(node.bases)
        self.visit(node.decorator_list)
        self.local_scope_visit(node.body)

    def visit_Delete(self, node):
        """del keyword.

        Reads and writes the expression (since it needs to exist).
        """
        for target in node.targets:
            self.visit(target)
            self.assign(target)

    def visit_Assign(self, node):
        """Assignment (equal sign).

        Writes the targets, reads the expression.
        """
        for target in node.targets:
            self.assign(target)
        self.visit(node.value)

    def visit_For(self, node):
        """For loop.

        Create a symbol in the current scope for the counter, since it will
        persist with the last value, and handle the body and iterator in the
        same scope.
        """
        self.assign(node.target)
        self.visit(node.iter)
        self.visit(node.body)

    def visit_With(self, node):
        """With block.

        Create a symbol in the current scope for the context managers, if the
        'as' keyword is used, and handle the context manager expression and the
        body in the same scope.
        """
        if node.optional_vars:
            self.assign(node.optional_vars)
        self.visit(node.context_expr)
        self.visit(node.body)

    def visit_TryExcept(self, node):
        """Try-except block without a finally clause.

        The handlers create symbols for the caught exceptions, the bodies are
        handled in the same scope.
        """
        self.visit(node.body)
        for handler in node.handlers:
            if handler.type is not None:
                self.visit(handler.type)
            if handler.name is not None:
                self.assign(handler.name)
            self.visit(handler.body)
        if node.orelse is not None:
            self.visit(node.orelse)

    def visit_Import(self, node):
        """Import keyword (without from).

        Without 'as', this creates a symbol for the first element in the dotted
        list.

        With 'as', this creates a symbol for the given name.
        """
        for name in node.names:
            if name.asname is not None:
                self.assign(name.asname)
            else:
                self.assign(name.name.split('.', 1)[0])

    def visit_ImportFrom(self, node):
        """From-import construct.

        Without 'as', this creates a symbol for the imported name.

        With 'as', this creates a symbol for the given name.
        """
        for name in node.names:
            if name.asname is not None:
                self.assign(name.asname)
            else:
                self.assign(name.name)

    def visit_Exec(self, node):
        """Exec keyword.

        Not much we can do here.
        """
        self.generic_visit(node)

    def visit_Global(self, node):
        """Global keyword.

        This marks a symbol name as non-local, such that assigning it will
        assign to the global scope.
        """
        if self.scopes:
            self.scopes[-1].globals.update(node.names)

    def visit_Name(self, node):
        """A variable reference.

        Mark it as read.
        """
        if self.in_global_scope or node.id not in self.scopes[-1].locals:
            self.cell.reads.add(node.id)

    def visit_Call(self, node):
        """A function call.

        If calling a method on an object, we mark that object as changed.

        We assume calling a function doesn't change the function, and that in
        any case arguments are left untouched.
        """
        if isinstance(node.func, ast.Attribute):
            self.assign(node.func.value)
        else:
            self.visit(node.func)
        self.visit(node.args)
        self.visit(node.keywords)
        self.visit(node.starargs)
        self.visit(node.kwargs)


class Cell(object):
    """A piece of code that can be parsed independently.

    Dependencies are only computed between cells, no analysis happens between
    the lines of a single cell.
    """
    def __init__(self, source):
        if isinstance(source, ast.AST):
            self.source = source
            logger.info("Parsing cell: %r", source)
        else:
            self.source = ast.parse(source)
            logger.info("Parsing cell:\n----------\n%s\n----------",
                        source.strip('\n'))

        self.reads = set()
        self.writes = set()

        visitor = _CellVisitor(self)
        visitor.visit(self.source)

        logger.info("Parsing done!\n  reads: %s\n  writes: %s",
                    ', '.join(self.reads),
                    ', '.join(self.writes))


class Flow(object):
    """A dataflow consisting of multiple cells.

    You can add, remove, and reorder cells from a Flow, and the dependencies
    will be updated automatically.
    """
    def __init__(self, cells=None):
        # Maps symbol names to the cells that use it
        self.read_by = {}
        # Maps symbols names to the cells that assign it
        self.written_by = {}

        if cells is not None:
            self._cells = list(cells)
        else:
            self._cells = [self._add(cell) for cell in cells]

    def _add(self, cell):
        if isinstance(cell, Cell):
            pass
        elif isinstance(cell, text):
            cell = Cell(cell)
        else:
            raise TypeError("Expected iterable of Cell or strings, "
                            "got %r" % type(cell))

        if cell.reads:
            for symbol in cell.reads:
                default(self.read_by, symbol, set).add(cell)

        if cell.writes:
            for symbol in cell.writes:
                default(self.written_by, symbol, set).add(cell)

        return cell

    def _rm(self, cell):
        for symbol in cell.reads:
            self.read_by[symbol].remove(cell)
        for symbol in cell.writes:
            self.written_by[symbol].remove(cell)

    def __iter__(self):
        return iter(self._cells)

    def __len__(self):
        return len(self._cells)

    def __getitem__(self, item):
        return self._cells[item]

    def __setitem__(self, key, value):
        self._rm(self._cells[key])
        self._cells[key] = self._add(value)

    def __setslice__(self, i, j, sequence):
        for cell in self._cells[i:j]:
            self._rm(cell)
        self._cells[i:j] = (self._add(cell) for cell in sequence)

    def __delitem__(self, key):
        self._rm(self._cells.pop(key))

    def __delslice__(self, i, j):
        for cell in self._cells[i:j]:
            self._rm(cell)
        del self._cells[i:j]

    def dependencies(self, cell):
        last_assign = {}
        symbols = set(cell.reads)

        for other in self._cells[self._cells.index(cell)::-1]:
            if not symbols:
                break
            for symbol in other.writes.intersection(symbols):
                last_assign[symbol] = other
            symbols.difference_update(other.writes)

        return set(itervalues(last_assign))

    def dependents(self, cell):
        last_read = {}
        symbols = set(cell.writes)

        for other in self._cells[self._cells.index(cell):]:
            if not symbols:
                break
            for symbol in other.reads.intersection(symbols):
                last_read[symbol] = other
            symbols.difference_update(other.reads)

        return set(itervalues(last_read))

    def graph(self):
        graph = {}
        last_assign = {}

        for cell in self._cells:
            deps = set()
            for symbol in cell.reads:
                try:
                    deps.add(last_assign[symbol])
                except KeyError:
                    pass
            graph[cell] = deps
            for symbol in cell.writes:
                last_assign[symbol] = cell

        return graph
