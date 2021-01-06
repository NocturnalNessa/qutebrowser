# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2021 Ryan Roden-Corrent (rcorre) <ryan@rcorre.net>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Module for parsing commands entered into the browser."""

import attr

from qutebrowser.commands import cmdexc
from qutebrowser.misc import split, objects


@attr.s
class ParseResult:

    """The result of parsing a commandline."""

    cmd = attr.ib()
    args = attr.ib()
    cmdline = attr.ib()


class CommandParser:

    """Parse qutebrowser commandline commands.

    Attributes:
        _partial_match: Whether to allow partial command matches.
    """

    def __init__(self, partial_match=False):
        self._partial_match = partial_match

    def _get_alias(self, text, aliases, default=None):
        """Get an alias from the config.

        Args:
            text: The text to parse.
            aliases: A map of aliases to commands.
            default : Default value to return when alias was not found.

        Return:
            The new command string if an alias was found. Default value
            otherwise.
        """
        parts = text.strip().split(maxsplit=1)
        if parts[0] not in aliases:
            return default
        alias = aliases[parts[0]]

        try:
            new_cmd = '{} {}'.format(alias, parts[1])
        except IndexError:
            new_cmd = alias
        if text.endswith(' '):
            new_cmd += ' '
        return new_cmd

    def _parse_all_gen(self, text, *args, aliases=None, **kwargs):
        """Split a command on ;; and parse all parts.

        If the first command in the commandline is a non-split one, it only
        returns that.

        Args:
            text: Text to parse.
            aliases: A map of aliases to commands.
            *args/**kwargs: Passed to parse().

        Yields:
            ParseResult tuples.
        """
        text = text.strip().lstrip(':').strip()
        if not text:
            raise cmdexc.NoSuchCommandError("No command given")

        if aliases:
            text = self._get_alias(text, aliases, text)

        if ';;' in text:
            # Get the first command and check if it doesn't want to have ;;
            # split.
            first = text.split(';;')[0]
            result = self.parse(first, *args, **kwargs)
            if result.cmd.no_cmd_split:
                sub_texts = [text]
            else:
                sub_texts = [e.strip() for e in text.split(';;')]
        else:
            sub_texts = [text]
        for sub in sub_texts:
            yield self.parse(sub, *args, **kwargs)

    def parse_all(self, *args, **kwargs):
        """Wrapper over _parse_all_gen."""
        return list(self._parse_all_gen(*args, **kwargs))

    def parse(self, text, *, fallback=False, keep=False, best_match=False):
        """Split the commandline text into command and arguments.

        Args:
            text: Text to parse.
            fallback: Whether to do a fallback splitting when the command was
                      unknown.
            keep: Whether to keep special chars and whitespace

        Return:
            A ParseResult tuple.
        """
        cmdstr, sep, argstr = text.partition(' ')

        if not cmdstr and not fallback:
            raise cmdexc.NoSuchCommandError("No command given")

        if self._partial_match:
            cmdstr = self._completion_match(cmdstr, best_match)

        try:
            cmd = objects.commands[cmdstr]
        except KeyError:
            if not fallback:
                raise cmdexc.NoSuchCommandError(
                    '{}: no such command'.format(cmdstr))
            cmdline = split.split(text, keep=keep)
            return ParseResult(cmd=None, args=None, cmdline=cmdline)

        args = self._split_args(cmd, argstr, keep)
        if keep and args:
            cmdline = [cmdstr, sep + args[0]] + args[1:]
        elif keep:
            cmdline = [cmdstr, sep]
        else:
            cmdline = [cmdstr] + args[:]

        return ParseResult(cmd=cmd, args=args, cmdline=cmdline)

    def _completion_match(self, cmdstr, best):
        """Replace cmdstr with a matching completion if there's only one match.

        Args:
            cmdstr: The string representing the entered command so far

        Return:
            cmdstr modified to the matching completion or unmodified
        """
        matches = [cmd for cmd in sorted(objects.commands, key=len)
                   if cmdstr in cmd]
        if len(matches) == 1:
            cmdstr = matches[0]
        elif len(matches) > 1 and best:
            cmdstr = matches[0]
        return cmdstr

    def _split_args(self, cmd, argstr, keep):
        """Split the arguments from an arg string.

        Args:
            cmd: The command we're currently handling.
            argstr: An argument string.
            keep: Whether to keep special chars and whitespace

        Return:
            A list containing the split strings.
        """
        if not argstr:
            return []
        elif cmd.maxsplit is None:
            return split.split(argstr, keep=keep)
        else:
            # If split=False, we still want to split the flags, but not
            # everything after that.
            # We first split the arg string and check the index of the first
            # non-flag args, then we re-split again properly.
            # example:
            #
            # input: "--foo -v bar baz"
            # first split: ['--foo', '-v', 'bar', 'baz']
            #                0        1     2      3
            # second split: ['--foo', '-v', 'bar baz']
            # (maxsplit=2)
            split_args = split.simple_split(argstr, keep=keep)
            flag_arg_count = 0
            for i, arg in enumerate(split_args):
                arg = arg.strip()
                if arg.startswith('-'):
                    if arg in cmd.flags_with_args:
                        flag_arg_count += 1
                else:
                    maxsplit = i + cmd.maxsplit + flag_arg_count
                    return split.simple_split(argstr, keep=keep,
                                              maxsplit=maxsplit)

            # If there are only flags, we got it right on the first try
            # already.
            return split_args
