# -*- coding: utf-8 -*-

import cgi
import types
from itertools import islice
from collections import Sequence, Mapping, MutableSequence


_MISSING = object()

"""
This Table class is meant to be simple, low-overhead, and extensible. Its
most common use would be for translation between in-memory data
structures and serialization formats, such as HTML and console-ready text.

As such, it stores data in list-of-lists format, and _does not_ copy
lists passed in. It also reserves the right to modify those lists in a
"filling" process, whereby short lists are extended to the width of
the table (usually determined by number of headers). This greatly
reduces overhead and processing/validation that would have to occur
otherwise.

General description of headers behavior:

Headers describe the columns, but are not part of the data, however,
if the `headers` argument is omitted, Table tries to infer header
names from the data. It is possible to have a table with no headers,
just pass in `headers=None`.

Supported inputs:

* list of lists
* dict (list/single)
* object (list/single)  (list TODO)
* TODO: namedtuple (list/single)
* TODO: sqlite return value
* TODO: json

Supported outputs:

* HTML
* Pretty text (also usable as GF Markdown)
* TODO: CSV
* TODO: json
* TODO: json lines

An abstract thought:

class Backend(object):
    row_type = list

    def _guess_headers(self):
        pass

Some idle thoughts:

* shift around column order without rearranging data
* gotta make it so you can add additional items, not just initialize with
* maybe a shortcut would be to allow adding of Tables to other Tables
* what's the perf of preallocating lists and overwriting items versus
  starting from empty?
"""


def escape_html(text):
    text = unicode(text)
    return cgi.escape(text, True)


_DNR = set([types.NoneType, types.BooleanType, types.IntType, types.LongType,
            types.ComplexType, types.StringType, types.UnicodeType,
            types.NotImplementedType, types.SliceType])  # function/method


class InputType(object):
    def __init__(self, *a, **kw):
        pass

    def get_entry_seq(self, data_seq, headers):
        return (self.get_entry(entry, headers) for entry in data_seq)


class DictInputType(InputType):
    def check_type(self, obj):
        return isinstance(obj, Mapping)

    def guess_headers(self, obj):
        return obj.keys()

    def get_entry(self, obj, headers):
        return [obj.get(h) for h in headers]

    def get_entry_seq(self, obj, headers):
        return ([ci.get(h) for h in headers] for ci in obj)


class ObjectInputType(InputType):
    def check_type(self, obj):
        return hasattr(obj, '__class__')

    def guess_headers(self, obj):
        headers = []
        for attr in dir(obj):
            # an object's __dict__ could have non-string keys but meh
            val = getattr(obj, attr)
            if callable(val):
                continue
            headers.append(attr)
        return headers

    def get_entry(self, obj, headers):
        values = []
        for h in headers:
            try:
                values.append(getattr(obj, h))
            except:
                values.append(None)
        return values


# might be better to hardcode list support since it's so close to the core
class ListInputType(InputType):
    def check_type(self, obj):
        return isinstance(obj, MutableSequence)

    def guess_headers(self, obj):
        return None

    def get_entry(self, obj, headers):
        return obj  # obj[0] ?

    def get_entry_seq(self, obj_seq, headers):
        return obj_seq


class Table(object):
    # order definitely matters here
    _input_types = [DictInputType(), ListInputType(), ObjectInputType()]

    def __init__(self, data=None, headers=_MISSING):
        if headers is _MISSING and data:
            headers, data = list(data[0]), islice(data, 1, None)
        self.headers = headers or []
        self._data = []
        self._width = 0
        self.extend(data)

    def extend(self, data):
        if not data:
            return
        self._data.extend(data)
        self._set_width()
        self._fill()

    def _set_width(self, reset=False):
        if reset:
            self._width = 0
        if self._width:
            return
        if self.headers:
            self._width = len(self.headers)
            return
        self._width = max([len(d) for d in self._data])

    def _fill(self):
        width, filler = self._width, [None]
        if not width:
            return
        for d in self._data:
            rem = width - len(d)
            if rem > 0:
                d.extend(filler * rem)
        return

    @classmethod
    def from_dict(cls, data, headers=_MISSING, max_depth=1):
        return cls.from_data(data=data, headers=headers,
                             max_depth=max_depth, _data_type=DictInputType())

    @classmethod
    def from_list(cls, data, headers=_MISSING, max_depth=1):
        return cls.from_data(data=data, headers=headers,
                             max_depth=max_depth, _data_type=ListInputType())

    @classmethod
    def from_object(cls, data, headers=_MISSING, max_depth=1):
        return cls.from_data(data=data, headers=headers,
                             max_depth=max_depth, _data_type=ObjectInputType())

    @classmethod
    def from_data(cls, data, headers=_MISSING, max_depth=1, _data_type=None):
        # TODO: seen/cycle detection/reuse ?
        # maxdepth follows the same behavior as find command
        # i.e., it doesn't work if max_depth=0 is passed in
        if max_depth < 1:
            return cls(headers=headers)  # return data instead?
        is_seq = isinstance(data, Sequence)
        if is_seq:
            if not data:
                return cls(headers=headers)
            to_check = data[0]
        else:
            if type(data) in _DNR:
                # hmm, got scalar data.
                # raise an exception or make an exception, nahmsayn?
                return Table([[data]], headers=headers)
            to_check = data
        if not _data_type:
            for it in cls._input_types:
                if it.check_type(to_check):
                    _data_type = it
                    break
                else:
                    raise TypeError('unsupported data type %r' % type(data))
        if headers is _MISSING:
            headers = _data_type.guess_headers(to_check)
        if is_seq:
            entries = _data_type.get_entry_seq(data, headers)
        else:
            entries = [_data_type.get_entry(data, headers)]
        if max_depth > 1:
            rec_entries = [None] * len(entries)
            new_max_depth = max_depth - 1
            for i, entry in enumerate(entries):
                rec_entries[i] = [cls.from_data(cell,
                                                max_depth=new_max_depth)
                                  if type(cell) not in _DNR else cell
                                  for cell in entry]
            entries = rec_entries
        return cls(entries, headers=headers)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, idx):
        return self._data[idx]

    def __repr__(self):
        cn = self.__class__.__name__
        if self.headers:
            return '%s(headers=%r, data=%r)' % (cn, self.headers, self._data)
        else:
            return '%s(%r)' % (cn, self._data)

    def to_html(self, orientation=None, wrapped=True,
                with_headers=True, with_newlines=True, max_depth=1):
        print self
        lines = []
        if wrapped:
            lines.append('<table>')
        orientation = orientation or 'auto'
        ol = orientation[0].lower()
        if ol == 'a':
            ol = 'h' if len(self) > 1 else 'v'
        if ol == 'h':
            self._add_horizontal_html_lines(lines, with_headers=with_headers,
                                            max_depth=max_depth)
        elif ol == 'v':
            self._add_vertical_html_lines(lines, with_headers=with_headers,
                                          max_depth=max_depth)
        else:
            raise ValueError("expected one of 'auto', 'vertical', or"
                             " 'horizontal', not %r" % orientation)
        if wrapped:
            lines.append('</table>')
        sep = '\n' if with_newlines else ''
        return sep.join(lines)

    def _add_horizontal_html_lines(self, lines, with_headers, max_depth):
        esc = escape_html
        new_depth = max_depth - 1 if max_depth > 1 else max_depth
        if max_depth > 1:
            new_depth = max_depth - 1
        if with_headers:
            lines.append('<tr><th>' +
                         '</th><th>'.join([esc(h) for h in self.headers]) +
                         '</th></tr>')
        for row in self._data:
            if max_depth > 1:
                _fill_parts = []
                for cell in row:
                    if isinstance(cell, Table):
                        _fill_parts.append(cell.to_html(max_depth=new_depth))
                    else:
                        _fill_parts.append(esc(cell))
            else:
                _fill_parts = [esc(c) for c in row]
            lines.append(''.join(['<tr><td>',
                                  '</td><td>'.join(_fill_parts),
                                  '</td></tr>']))

    def _add_vertical_html_lines(self, lines, with_headers, max_depth):
        esc = escape_html
        new_depth = max_depth - 1 if max_depth > 1 else max_depth
        for i in range(self._width):
            line_parts = ['<tr>']
            if with_headers:
                line_parts.extend(['<th>', esc(self.headers[i]), '</th>'])
            if max_depth > 1:
                new_depth = max_depth - 1
                _fill_parts = []
                for row in self._data:
                    cell = row[i]
                    if isinstance(cell, Table):
                        _fill_parts.append(cell.to_html(max_depth=new_depth))
                    else:
                        _fill_parts.append(esc(row[i]))
            else:
                _fill_parts = [esc(row[i]) for row in self._data]
            _fill = '</td><td>'.join(_fill_parts)
            line_parts.extend(['<td>', _fill, '</td></tr>'])
            lines.append(''.join(line_parts))

    def to_text(self, with_headers=True):
        # TODO: verify this works for markdown
        lines = []
        widths = []
        headers = self.headers
        for idx in range(self._width):
            cur_widths = [len(unicode(cur[idx])) for cur in self._data]
            if with_headers:
                cur_widths.append(len(headers[idx]))
            widths.append(max(cur_widths))
        if with_headers:
            lines.append(' | '.join([h.center(widths[i])
                                     for i, h in enumerate(headers)]))
            lines.append('-+-'.join(['-' * w for w in widths]))
        for row in self._data:
            lines.append(' | '.join([unicode(col).center(widths[j])
                                     for j, col in enumerate(row)]))
        return '\n'.join(lines)


def main():
    data_dicts = [{'id': 1, 'name': 'John Doe'},
                  {'id': 2, 'name': 'Dale Simmons'}]
    data_lists = [['id', 'name'],
                  [1, 'John Doe'],
                  [2, 'Dale Simmons']]
    t1 = Table(data_lists)
    t2 = Table.from_dict(data_dicts[0])
    t3 = Table.from_dict(data_dicts)
    t3.extend([[3, 'Kurt Rose'], [4]])
    print t1
    print t2
    print t2.to_html()
    print t3
    print t3.to_html()
    print t3.to_text()

    import re
    t4 = Table.from_object(re.compile(''))
    print t4.to_text()
    import pdb;pdb.set_trace()


if __name__ == '__main__':
    main()
