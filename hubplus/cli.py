import click
import subprocess
import os
import re
import requests
import sys
import tempfile

_current_repo = None
_current_branch = None
_github_oauth_token = None

@click.command()
@click.option('--assignee', '-a', is_flag=False, help='The github handle of the person you wish to assign.')
@click.option('--browse', '-o', is_flag=True, help='Open the resulting PR in your browser')
@click.option('--force', '-f', is_flag=True, help='Force open the PR even if there are unpushed changes on the current branch')
@click.option('--file', '-F', is_flag=False, help='Path to a file that will be read to populate the PR\'s first comment\'s content')
@click.option('--message', '-m', is_flag=False, help='A string that will populate the PR\'s first comment\'s content')
@click.option('--issue', '-i', is_flag=False, help='An existing issue ID or URL that will be converted into a PR with this branch')
@click.option('--base', '-b', is_flag=False, help='The base branch of the PR; the branch you want to merge your changes into')
@click.option('--head', '-h', is_flag=False, help='The head branch of the PR; the branch that has your changes')
def main(assignee, browse, force, file, message, issue, base, head):
    """
    Opens a pull request on GitHub for the project  that  the  "origin"
    remote points to. The default head of the pull request is the cur-
    rent branch. Both base and head of the pull request can be explic-
    itly given in one of the following formats: "branch",
    "owner:branch", "owner/repo:branch". This command will abort opera-
    tion if it detects that the current topic branch has local commits
    that are not yet pushed to its upstream branch on the remote. To
    skip this check, use -f.

    Without MESSAGE or FILE, a text editor will open in which title and
    body of the pull request can be entered in the same manner as git
    commit message. Pull request message can also be passed via stdin
    with -F -.

    With -o or --browse, the new pull request will open in the web
    browser.

    Issue to pull request conversion via -i <ISSUE> or ISSUE-URL argum-
    ents is deprecated and will likely be removed from the future vers-
    ions of both hub and GitHub API.

    You also must pass in an assignee's github handle via the --assignee
    or -a option. This extention to github's `hub` will assign that user
    and label the pull-request as in need of review.
    """
    # Above is copy/pasted from `man hub`

    branch_ready, error_msg = current_branch_is_pushed()
    if not branch_ready:
        if force:
            click.echo("force-opening not yet supported")
        else:
            raise Exception(error_msg)

    assignment_label = get_assignment_label()
    if assignment_label is None:
        raise Exception("No label with the text 'review' and without the text 'self' found")

    if not validate_assignee(assignee):
        raise Exception("No assignee named {} found".format(assignee))

    if not message and not file:
        message = get_message()

    issue_number = create_pull_request(browse, force, file, message, issue, base, head)

    if not label_and_assign(issue_number, assignment_label, assignee):
        raise Exception("Failed to mark issue {issue_number} with label {label} and assign {assignee}".format(
            issue_number=issue_number,
            label=assignment_label,
            assignee=assignee
        ))

    click.echo('PR opened!')


def syscall(cmd, return_stdout=False):
    print('>', cmd)
    if return_stdout:
        output = subprocess.check_output(cmd, shell=True)
        if type(output) is bytes:
            return output.decode("utf-8")
        return str(output)
    else:
        return subprocess.call(cmd, shell=True, stdout=open(os.devnull, 'wb'))


def current_branch_is_pushed():
    fetch_result = syscall("git fetch")
    if fetch_result != 0:
        raise Exception("Was unable to call git fetch")
    diff_result = syscall("git diff --cached --exit-code")
    if diff_result != 0:
        # TODO: probably have cmd line prompt "are you sure you want to push even though you have uncommitted local changes?"
        return False, "Uncommitted changes in local working directory"

    current_branch = get_current_branch_name()
    branch_diff_cmd = "git diff --exit-code {branch} origin/{branch}".format(
        branch=current_branch
    )
    diff_origin_result = syscall(branch_diff_cmd)
    if diff_origin_result != 0:
        return False, "Unpushed local changes"
    return True, None


def get_current_branch_name():
    global _current_branch

    if _current_branch:
        return _current_branch

    exception = None
    try:
        branch_name_or_exception_msg = syscall("git symbolic-ref HEAD 2>/dev/null", return_stdout=True)
        branch_name_or_exception_msg = branch_name_or_exception_msg.split('refs/heads/')[-1].strip()
        _current_branch = branch_name_or_exception_msg
    except Exception as e:
        exception = True
        branch_name_or_exception_msg = exception
    if exception or not branch_name_or_exception_msg or not type(branch_name_or_exception_msg) is str:
        raise Exception("Got invalid branch name {}".format(branch_name_or_exception_msg))
    return branch_name_or_exception_msg


def get_assignment_label():
    labels = get_remote_labels()
    for label in labels:
        if 'review' in label and 'self' not in label:
            return label
    return None


def get_current_repo():
    global _current_repo

    if _current_repo:
        return _current_repo

    remotes = syscall("git remote -v", return_stdout=True)
    matches = re.match(r'.*github\.com.([^\s]*)', remotes)
    if matches:
        _current_repo = matches.group(1).split('.git')[0]
        return _current_repo
    else:
        raise Exception("Could not figure out current repo URL")


def get_github_api_url_base():
    return "https://api.github.com/repos/{owner_and_repo}".format(
        owner_and_repo=get_current_repo(),
    )


def get_github_oauth_token_header_value():
    global _github_oauth_token

    if not _github_oauth_token:
        with open(os.path.expanduser('~/.config/hub'), 'r') as hub_config_file:
            hub_config = hub_config_file.read()
            matches = re.match(r'.*oauth_token: ([\S]*)', hub_config, re.DOTALL)
            if matches:
                _github_oauth_token = matches.group(1)
            else:
                raise Exception("Could not find oauth token in ~/.config/hub")

    return "token {}".format(_github_oauth_token)


def get_github_oauth_token_header():
    return {'Authorization': get_github_oauth_token_header_value()}


def get_remote_labels():
    url = get_github_api_url_base()
    url += '/labels'
    response = requests.get(url, headers=get_github_oauth_token_header())
    return [label['name'] for label in response.json()]


def validate_assignee(assignee):
    assignees = get_remote_assignees()
    for candidate in assignees:
        if assignee == candidate:
            return candidate
    return None


def get_remote_assignees():
    url = get_github_api_url_base()
    url += '/assignees'
    response = requests.get(url, headers=get_github_oauth_token_header())
    return [person['login'] for person in response.json()]


def get_message():
    # If we want a template
    initial_message = ""

    result = raw_input_editor(default=initial_message)
    return result


def raw_input_editor(default=None, editor=None):
    with tempfile.NamedTemporaryFile(mode='r+') as tmpfile:
        if default:
            tmpfile.write(default)
            tmpfile.flush()
        subprocess.check_call([editor or get_editor(), tmpfile.name])
        tmpfile.file.close()
        with open(tmpfile.name) as tmpfile2:
            return tmpfile2.read().strip()


def get_editor():
    return (os.environ.get('VISUAL')
        or os.environ.get('EDITOR')
        or 'vi')


def create_pull_request(browse, force, file, message, issue, base, head):
    command = ["hub pull-request"]
    if browse:
        command.append("-o")
    if force:
        command.append("-f")
    if file:
        command.append("-F \"{}\"".format(file))
    if message:
        command.append("-m \"{}\"".format(message))
    if issue:
        command.append("-i \"{}\"".format(issue))
    if base:
        command.append("-b \"{}\"".format(base))
    if head:
        command.append("-h \"{}\"".format(head))
    branch_url = syscall(' '.join(command), return_stdout=True)
    return branch_url.strip().split('/')[-1]


def label_and_assign(issue_number, assignment_label, assignee):
    url = get_github_api_url_base()
    url += '/issues/{issue_number}'.format(issue_number=issue_number)
    body = {
       "assignee": assignee,
       "labels": [assignment_label]
    }
    response = requests.post(url, headers=get_github_oauth_token_header(),
                             json=body)
    return response.status_code == 200
