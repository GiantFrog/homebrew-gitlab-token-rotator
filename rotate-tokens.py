import argparse
from datetime import datetime, timedelta, timezone
import gitlab
import keyring
from os import environ
import pyperclip
from sys import exit
import webbrowser

parser = argparse.ArgumentParser(
    description="\033[1mGitlab Token Rotator\033[0m"
)
parser.add_argument(
    '-i', '--instance',
    # default is set manually later so we can check env variables first
    help="The URL of the Gitlab instance you'd like to use. (default: https://gitlab.com)"
)
parser.add_argument(
    '-l', '--lifetime',
    type=int,
    default=365,
    help="How many days until the tokens we create expire! Gitlab defaults to 7 days, which is pathetic, so this tool defaults to the max value of 1 year. (default: 365)"
)
parser.add_argument(
    '-f', '--freshness',
    type=int,
    default=14,
    help="If a token was created or renewed within this many days, it's new, and we will silently ignore it. (default: 14)"
)
args = parser.parse_args()
# If the user didn't specify an instance, let's try to pull from the env variables first.
if args.instance is None:
    args.instance = environ.get('GITLAB_INSTANCE')
# If it's still None after that, THEN we assume they just mean gitlab.com
if args.instance is None:
    args.instance = "https://gitlab.com"
# Otherwise, make sure the user-provided arg or env var is formatted with a protocol and no trailing slash.
else:
    if '//' not in args.instance:
        args.instance = f"https://{args.instance}"
    if args.instance[-1] == '/':
        args.instance = args.instance[:-1]


def needs_rotation(token):
    created_days_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(token.created_at)).days
    if token.revoked or token.expires_at is None:
        return False    # don't care
    if token.id == this_scripts_token.id:
        return False    # let's wait to renew our own token until after we finish everything else!
    if created_days_ago < args.freshness:
        return False    # this token was just updated; let's not bother.
    return True

def process_token(token):
    print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――")
    expiry_date = datetime.strptime(token.expires_at, '%Y-%m-%d')
    created_days_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(token.created_at)).days
    print(f"{token.name}{' - EXPIRED' if expiry_date < datetime.today() else ''}{' - NEVER USED' if token.last_used_at is None else ''}")
    if expiry_date >= datetime.today():
        print(f"Expires in {(expiry_date - datetime.today()).days} days.")
    print(f"Created {created_days_ago} days ago.")
    if token.last_used_at is not None:
        used_datetime = datetime.fromisoformat(token.last_used_at)
        print(f"Last used {(datetime.now(timezone.utc) - used_datetime).days} days ago.")

    print("\nWhat would you like to do with this token?")
    while True:
        match input("  (r)otate it, (d)elete it, or (i)gnore this time: ")[:1].lower():
            case 'r':
                print("Here's your new token! It's been copied to your clipboard.")
                token.rotate(expires_at=new_expiration_date)
                print(token.token)
                pyperclip.copy(token.token)
                input("Save it wherever it's used, then press enter to continue...")
                return True
            case 'd':
                if input(f"Are you sure you want to delete the token '{token.name}'? (y/n) ")[:1].lower() == 'y':
                    print("Okay, got rid of that one!")
                    token.delete()
                    # the final dialog makes more sense if we don't flag deletions as having done a rotation
                    return False
                else:
                    print("Never mind then, going back...")
            case 'i':
                return False
            case _:
                print("Unrecognized input. Try again? Just type r, d, or i.")


if __name__ == '__main__':
    # INITIALIZE!
    access_token = keyring.get_password('GitLab Token Rotator', args.instance)
    while True:
        if access_token is None:    # no token was saved in the keychain. first execution?
            print(f"First run on instance {args.instance}...\nYou'll need an access token with 'api' permissions to manage all your tokens! We'll save it in your computer's keychain.")
            input("Press enter to open GitLab, then make a new 'Token Rotator' token with only the 'api' box checked...")
            webbrowser.open(f"{args.instance}/-/user_settings/personal_access_tokens")
            input("Copy your new access token from the site, then press enter! (We'll load it from your clipboard.)")
            access_token = pyperclip.paste()
            keyring.set_password('GitLab Token Rotator', args.instance, access_token)
        try:
            gl = gitlab.Gitlab(args.instance, private_token=access_token, user_agent='gitlab_token_rotator/1.0')
            gl.auth()
            print(f"Logged in as {gl.user.name}!")
            break
        except Exception as error:
            print(f"Could not authenticate with your token '{access_token}'!\n{error}")
            match input("  (e)xit, (n)ew token, or just hit enter to try again with the same token: ")[:1].lower():
                case 'e':
                    exit(221)
                case 'n':
                    access_token = None

    print("WARNING: Rotating a token immediately revokes the old one. The gitlab API does not include a feature to undo this action.\n\033[1mPlease make sure you're in a position to actually put the new token where it needs to go before you choose to rotate it!\033[0m")
    new_expiration_date = (datetime.today() + timedelta(days=args.lifetime)).strftime('%Y-%m-%d')
    our_user = gl.users.get(gl.user.id, lazy=True)
    this_scripts_token = gl.personal_access_tokens.get("self")
    we_did_something = False

    # USER PERSONAL ACCESS TOKENS
    for t in gl.personal_access_tokens.list(user_id=gl.user.id, iterator=True):
        # if the token is due for rotation, see if the user wants to rotate it.
        if needs_rotation(t):
            if process_token(t):
                we_did_something = True

    # USER PROJECT TOKENS
    for partial_project_object in our_user.projects.list(iterator=True):
        project = gl.projects.get(partial_project_object.id, lazy=True)
        tokens = project.access_tokens.list(get_all=True)
        if not any(tokens):
            continue
        tokens[:] = [t for t in tokens if needs_rotation(t)]
        if not any(tokens):
            print(f"Looks like \033[1m{project.name}\033[0m's tokens are all fresh within {args.freshness} days.")
            continue
        for t in tokens:
            if process_token(t):
                we_did_something = True

    # GROUP TOKENS
    for membership in our_user.memberships.list(type='Namespace', iterator=True):
        print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――\nProcessing all of the projects in each of your groups. This may take a few minutes!")
        # Collect all the tokens belonging to this group and its projects.
        group = gl.groups.get(membership.source_id)
        group_tokens = group.access_tokens.list(get_all=True)
        group_tokens[:] = [t for t in group_tokens if needs_rotation(t)]
        project_tokens = {}
        for partial_project_object in group.projects.list(iterator=True):
            project = gl.projects.get(partial_project_object.id)
            tokens = project.access_tokens.list(get_all=True)
            tokens[:] = [t for t in tokens if needs_rotation(t)]
            if any(tokens):
                project_tokens[project.name] = tokens

        # If there are any to process, let the user decide if they want to handle this group or not.
        if not (any(group_tokens) or any(project_tokens)):
            print(f"\033[1m{group.name}\033[0m doesn't have any tokens in need of rotation.")
            continue
        print(f"Found tokens to renew for group \033[1m{group.name}\033[0m!")
        if input("  (i)gnore all, or press enter to continue: ")[:1].lower() == 'i':
            continue

        # Iterate through every token in need of rotation.
        for t in group_tokens:
            if process_token(t):
                we_did_something = True
        for project_name, tokens in project_tokens:
            print(f"Project: \033[1m{project_name}\033[0m")
            for t in tokens:
                if process_token(t):
                    we_did_something = True

    # Finally, let's renew our own token without any effort on the part of the user.
    print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――")
    if this_scripts_token and args.freshness <= (datetime.now(timezone.utc) - datetime.fromisoformat(this_scripts_token.created_at)).days:
        print(f"Auto-renewing my own access token '{this_scripts_token.name}'...")
        this_scripts_token.rotate(expires_at=new_expiration_date)
        keyring.set_password('GitLab Token Rotator', args.instance, this_scripts_token.token)
    if we_did_something:
        print(f"All done! Enjoy your fresh tokens! They will expire on {new_expiration_date}, so mark your calendar before then.")
    else:
        print(f"You don't have any tokens that need rotating!\n(Tokens created up to {args.freshness} days ago are considered fresh and not in need of rotation.)")
