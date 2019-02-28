import util
import git

repo = git.repo.Repo("/tmp/CRPropa3")
rg = util.build_inverse_graph(repo,
                              [(repo.heads.master.commit.hexsha, "master"),
                               (repo.heads.lmaster.commit.hexsha, "lmaster"),
                               (repo.heads.tf17field.commit.hexsha, "tf17field")])
result = util.rewrite_commit_parents_recursive(repo, rg, "4082b5808a2d65c622e932f71eae373c61ad8487", ["d4ce2f516b8d693738f3957f8ead5ad10f044977"])

print(result[repo.heads.master.commit.hexsha])
