from git import Repo
from .builder import TreeNode
from collections import defaultdict
from colorama import Fore, Style
from datetime import datetime
import re
import subprocess

class TreePrinter:
    def __init__(self, repo, node_printer):
        if repo is None:
            raise ValueError("repo is null")
        if node_printer is None:
            raise ValueError("node printer is null")
        self.repo = repo
        self.node_printer = node_printer

    def print_tree(self, root_node):
        if root_node is None:
            raise ValueError("root node is null")
        self._print_node(root_node, "")

    def _skip(self, node, max=20):
        prev_nodes = []
        sorted_children = self._sorted_children(node)
        idx = 0
        while len(sorted_children) == 1:
            # Keep track of the last `max` children
            prev_nodes.append(node)
            if (len(prev_nodes) > max):
                prev_nodes.pop(0)

            # Traverse
            node = sorted_children[0]
            sorted_children = self._sorted_children(node)

        return prev_nodes[0] if len(prev_nodes) > 0 else node

    def _print_node(self, node, prefix, depth=0):
        main_graph_connector = ""
        for i, child in enumerate(self._sorted_children(node)):
            skipped_child = self._skip(child)
            self._print_node(skipped_child, prefix + main_graph_connector + (" " if i > 0 else ""), 0)

            if child != skipped_child:
                print(prefix + "╷ ...")
                print(prefix + "╷")

            child_is_head = (self.repo.head.commit == child.commit) if child.commit is not None else False

            # Print the child node
            summary = self.node_printer.node_summary(child)

            # Add padding lines to reach at least the minimum desired number of line
            min_summary_len = 2
            if len(summary) < min_summary_len:
                summary += [""] * (min_summary_len - len(summary))

            # 1st line
            bullet = Style.BRIGHT + Fore.CYAN + "⮕ " + Fore.RESET + Style.NORMAL if child_is_head else "◯"
            if i == 0:
                graph = main_graph_connector + bullet
            else:
                graph = main_graph_connector + " " + bullet
            print(prefix + graph + " " + summary.strip())

            # Update the connector character
            graph_connector = "┃" if child.is_direct_child() else "⋮"
            if i == 0:
                main_graph_connector = graph_connector

            # 2nd line
            if i == 0:
                graph = main_graph_connector
            else:
                graph = main_graph_connector + "/ "
            #print(prefix + graph + "  " + summary[1])

            if i > 0:
                main_graph_connector = graph_connector

            # Remaining lines
            #if i == 0:
            #    graph = main_graph_connector
            #else:
            #    graph = graph_connector + "  "
            #for line in summary[2:]:
            #    print(prefix + graph + "  " + line)


            # Spacing to parent node
            #if i < len(node.children) - 1:
            #    graph = main_graph_connector
            #else:
            #    graph = graph_connector
            print(prefix + graph)

    def _sorted_children(self, node):
        def compare(x):
            if x.is_on_master_branch:
                return 0
            return x.commit.committed_date
        return sorted(node.children, key=compare)

class TreeNodePrinter:
    def __init__(self, repo, refmap):
        self.repo = repo
        self.refmap = refmap
        res = subprocess.run(['git', 'status', '-b', '--porcelain'], capture_output=True, text=True)
        self.gitBranch = re.sub(r"\.\.\..*$", "", re.sub(r"[#\s]*", "", res.stdout))
        print("cur branch is " + self.gitBranch)

    def node_summary(self, node):
        """
        This method returns a summary description for a given node
        The structure for this is:
        - line 1: sha author [branches] relative_time
        - line 2: commit summary (first line of message)
        """
        if node.commit is None:
            return []

        # pprint(dir(node.commit))

        # refs
        refs = []
        if self.refmap is not None:
            refs = self.refmap.get(node.commit)
            # refs = {ref for ref in refs if "origin" not in ref}

        # Format the first line and start with the short sha
        line = ""
        sha = self.repo.git.rev_parse(node.commit.hexsha, short=True)
        is_head = (self.repo.head.commit == node.commit) if node.commit is not None else False
        if is_head:
            line += Style.BRIGHT + Fore.CYAN + sha + Fore.RESET + Style.NORMAL + "  "
        elif len(refs) > 0:
            line += Style.BRIGHT + Fore.YELLOW + sha + Fore.RESET + Style.NORMAL + "  "
        else:
            line += Style.NORMAL + Fore.WHITE + sha + Fore.RESET + "  "

        # Add the commit date as a relative string
        line += Style.BRIGHT + Fore.BLUE + self.format_commit_date(node.commit.committed_date) + Fore.RESET + Style.NORMAL

        line += " " + (node.commit.summary) + " "

        # Add any diffs
        diff = self.differential_revision(node.commit)
        if diff is not None:
            line += Fore.BLUE + diff + "  " + Fore.RESET

        # Add the branch names
        if len(refs) > 0:
            line += "(" + ", ".join(map(lambda b: self.colorized_branchname(b), refs)) + ")  " + Fore.RESET

        # Add the author
        author = node.commit.author.email.rsplit("@")[0]
        line += author + "  "

        return line

    def colorized_branchname(self, bname):
        if bname == self.gitBranch:
            return Style.BRIGHT + Fore.CYAN + bname + Fore.RESET + Style.NORMAL
        if bname in ['main', 'master']:
            return Style.BRIGHT + Fore.MAGENTA + bname.upper() + Fore.RESET + Style.NORMAL
        if 'origin' in bname:
            return Fore.GREEN + bname + Fore.RESET
        return Style.BRIGHT + Fore.GREEN + bname + Fore.RESET + Style.NORMAL



    def differential_revision(self, commit):
        if commit is None:
            return None

        diff_line_prefix = "Differential Revision:"
        lines = commit.message.splitlines()
        for l in lines:
            if l.startswith(diff_line_prefix):
                l = l[len(diff_line_prefix):]
                return l.strip().rsplit('/', 1)[-1]
        return None


    def format_commit_date(self, timestamp):
        if timestamp is None:
            return "Now"

        then = datetime.utcfromtimestamp(timestamp)
        diff = datetime.utcnow() - then

        second_diff = diff.seconds
        day_diff = diff.days

        if day_diff < 0:
            return "<Invalid time>"

        if day_diff == 0:
            if second_diff < 10:
                return "just now"
            if second_diff < 60:
                return str(second_diff) + "s"
            if second_diff < 3600:
                return str(round(second_diff / 60)) + "m"
            if second_diff < 86400:
                return str(round(second_diff / 3600)) + "h"
        if day_diff == 1:
            return "Yesterday"
        if day_diff < 7:
            return str(day_diff) + "d"
        if day_diff < 31:
            return str(round(day_diff / 7)) + "wk"

        return then.strftime("%Y-%m-%d")


class RefMap:
    """
    This class can quickly map from a commit sha to a list of names (heads).
    """
    def __init__(self, head_ref):
        self.head_ref = head_ref
        self.map = defaultdict(set)

        if self.head_ref.is_detached:
            self.map[self.head_ref.commit.hexsha].add("HEAD")

    def add(self, ref):
        if not ref:
            return
        #if not self.head_ref.is_detached and self.head_ref.ref == ref:
        #    name = "HEAD -> " + ref.name
        #else:
        name = ref.name
        self.map[ref.commit.hexsha].add(name)

    def get(self, commit):
        refs = list(self.map[commit.hexsha])
        refs.sort(key=lambda ref: "zzz" + ref if ref.startswith("origin") else ref)
        return refs
