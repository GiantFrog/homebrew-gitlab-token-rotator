# Gitlab Token Rotator
Starting with version 16.0, Gitlab now enforces token expiration. This can be a pain, especially considering different kinds of tokens live on different pages (and the UI to rotate your tokens wasn't even added until version 17.7!). The purpose of this software is to provide an efficient CLI interface where you can quickly rotate all of your tokens in one spot.

## Installation
```
brew tap GiantFrog/gitlab-token-rotator
brew install gitlab-token-rotator
```
This seems to take a while. I'm new to Homebrew, so I'm not sure how to best optimize install times.

## Usage
Run `gitlab-token-rotator` in a terminal!
```
options:
  -h, --help            show this help message and exit
  -i INSTANCE, --instance INSTANCE
                        The URL of the Gitlab instance you'd like to use, with the protocol, but no trailing slash. (default: https://gitlab.com)
  -l LIFETIME, --lifetime LIFETIME
                        How many days until the tokens we create expire! Gitlab defaults to 7 days, which is pathetic, so this tool defaults to the max value of 1 year. (default: 365)
  -f FRESHNESS, --freshness FRESHNESS
                        If a token was created or renewed within this many days, it's new, and we will silently ignore it. (default: 14)
```
If you primarily use a private Gitlab instance and would like to change the default instance permanently, you can set `GITLAB_INSTANCE` in your environment variables. Add a line like this to your `~/.zshrc`, `~/.bashrc`, or wherever env variables are sold.
```
export GITLAB_INSTANCE="https://gitlab.example.com"
```
If no protocol is provided, https is assumed. 
