import git

def convert_to_commit_date(date, offset):
    return "{} {}".format(date, git.objects.util.altz_to_utctz_str(offset))

def get_author_date(commit):
    return convert_to_commit_date(commit.authored_date, commit.author_tz_offset)

def get_commit_date(commit):
    return convert_to_commit_date(commit.committed_date, commit.committer_tz_offset)

def rewrite_commit_parents(repo, commit, new_parents):
    new_parents = [repo.commit(parent) for parent in new_parents]
    return git.objects.commit.Commit.create_from_tree(
        repo=repo,
        tree=commit.tree,
        message=commit.message,
        parent_commits=new_parents,
        author=commit.author,
        committer=commit.committer,
        author_date=get_author_date(commit),
        commit_date=get_commit_date(commit)
    )

class PendingCommit (object):

    def __init__(self, sha, waiting_on):
        self.sha = sha
        self.waiting_on = waiting_on

def rewrite_commit_parents_recursive(repo, reverse_graph, commit_sha, new_parents):
    assert(commit_sha in reverse_graph.keys())

    touched_branches = set()
    # whenever we find a commit that's signed in the original version,
    # we'll replace it with the signed version in the reconstructed history
    signed_commits = identify_signed_commits(repo, reverse_graph)

    rewritten_commit = rewrite_commit_parents(repo, repo.commit(commit_sha), new_parents)
    print("Rewritten initial commit:")
    print(rewritten_commit)

    rewritten_commits = {commit_sha: rewritten_commit.hexsha}
    print("Initial rewritten_commits:")
    print(rewritten_commits)
    pending_commits = {}
    rewrite_queue = reverse_graph[commit_sha].children[:]
    print(rewrite_queue)

    while len(rewrite_queue) > 0:
        commit_sha = rewrite_queue.pop()
        touched_branches.add(reverse_graph[commit_sha].starting_point)

        print("\nRewriting Commit: {}\n=============\n".format(commit_sha))

        new_parents = [rewritten_commits.get(parent.hexsha) or parent.hexsha
                       for parent in repo.commit(commit_sha).parents]

        print(" - parents: new - old")
        print("\n".join("   {} {}".format(new, old) for (new, old) in zip(new_parents, repo.commit(commit_sha).parents)))

        rewritten_commit = rewrite_commit_parents(repo, repo.commit(commit_sha), new_parents)

        # if the original history (from Lukas's repo) has a signed version
        # of this commit, use the signed commit's sha instead.
        if rewritten_commit.hexsha in signed_commits.keys():
            print(" - found signed version of commit, replacing")
            rewritten_commits[commit_sha] = signed_commits[rewritten_commit.hexsha]
        else:
            rewritten_commits[commit_sha] = rewritten_commit.hexsha

        for child_sha in reverse_graph[commit_sha].children:
            print(" - checking child: {}".format(child_sha))
            parents = repo.commit(child_sha).parents
            if len(parents) == 1:
                print("     has 1 parent, adding child to rewrite queue directly")
                assert(parents[0].hexsha == commit_sha)
                rewrite_queue.append(child_sha)

            else:
                print("     has more than one parent, checking pending_commits")
                if child_sha in pending_commits.keys():
                    pending_commit = pending_commits[child_sha]
                    pending_commit.waiting_on.remove(commit_sha)

                    if len(pending_commit.waiting_on) == 0:
                        rewrite_queue.append(pending_commit.sha)

                else:
                    waiting_on = [parent.hexsha for parent in parents if parent.hexsha not in rewritten_commits.keys()]
                    pending_commits[child_sha] = PendingCommit(child_sha, waiting_on)

    assert(len([commit for commit in pending_commits.values() if len(commit.waiting_on) > 0]) == 0)
    print("\ncommits from the following branches were rewritten:\n  {}".format("".join(touched_branches)))
    return rewritten_commits

class ReverseGraphCommit(object):
    def __init__(self, sha, starting_point, children):
        self.sha = sha
        self.starting_point = starting_point
        self.children = children

def build_inverse_graph(repo, starting_points):

    commits_to_do = [ReverseGraphCommit(starting_point[0], starting_point[1], [])
                     for starting_point in starting_points]
    commits = {commit.sha: commit for commit in commits_to_do}

    while len(commits_to_do) > 0:
        commit = commits_to_do.pop()
        for parent in repo.commit(commit.sha).parents:

            if parent.hexsha in commits.keys():
                parent_rgc = commits[parent.hexsha]
                assert(commit.sha not in parent_rgc.children)
                parent_rgc.children.append(commit.sha)

            else:
                parent_rgc = ReverseGraphCommit(parent.hexsha, commit.starting_point, [commit.sha])
                commits_to_do.append(parent_rgc)
                commits[parent.hexsha] = parent_rgc

    return commits
    
# iterates over all commits present in reverse_graph.
# returns a dictionary: for each signed commit, the
# corresponding unsigned commit hash is computed, and stored
# in the following way: {unsigned_commit_hash: signed_commit_hash}
def identify_signed_commits(repo, reverse_graph):

    signed_commits = {}

    for commit_sha in reverse_graph.keys():
        commit = repo.commit(commit_sha)

        if commit.gpgsig:
            # call rewrite commit parents with the same parents,
            # which will result in exactly the same commit, except with
            # a missing signature
            unsigned_commit = rewrite_commit_parents(repo, commit, commit.parents)
            signed_commits[unsigned_commit.hexsha] = commit_sha

    return signed_commits
