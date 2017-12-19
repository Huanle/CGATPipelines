#!/usr/bin/env bash

# Takes as input two conda env files:
# * the first one is expected as output generated by cgat_conda_deps.sh
# * the second one is expected as output generated by "conda env export"

# The expected output is a new conda env file matching conda packages
# listed in the first file with the version numbers listed in the second.

SCRIPT_NAME="$0"
SCRIPT_OPTS="$@"
TMP_ENV=$(mktemp)
TMP_EXP=$(mktemp)

## auxiliary functions

# function to report issues and exit
report_problem() {
   echo
   echo $1
   echo
   echo " Aborting. "
   exit 1
}


# function to get the relevant package names and versions
process_env_file() {
   egrep -v '^name|^channels|bioconda|conda-forge|defaults|^dependencies|pip|bx-python|#|^prefix|^ ' $1 \
    | sed 's/^- //g' \
    | sed 's/=/ /g' \
    | awk '{print $1" "$2}' \
    | sort -u > $2
}


# function to display help message
help_message() {
   echo
   echo " Takes as input two conda env files:"
   echo " * the first one is expected as output generated by cgat_conda_deps.sh"
   echo " * the second one is expected as output generated by 'conda env export'"
   echo
   echo " The expected output is a new conda env file matching conda packages"
   echo " listed in the first file with the version numbers listed in the second."
   echo
   echo " ./match_conda_deps.sh scripts-nosetests-template.yml conda-env-export.yml "
   echo
   exit 1
}


## the script starts here

if [[ $# -ne 2 ]] ; then

   help_message

fi

[[ ! -r $1 ]] && report_problem " File $1 is not readable. "
[[ ! -r $2 ]] && report_problem " File $2 is not readable. "

process_env_file $1 ${TMP_ENV}
process_env_file $2 ${TMP_EXP}

echo
echo "# output generated by ${SCRIPT_NAME} ${SCRIPT_OPTS}"
echo "# on `date`"
echo
echo "name: cgat-p"
echo
echo "channels:"
echo "- bioconda"
echo "- conda-forge"
echo "- defaults"
echo
echo "dependencies:"

# join tutorial
# https://shapeshed.com/unix-join/
join ${TMP_ENV} ${TMP_EXP} | egrep -v '^$' | awk '{print $1"="$2}' | sed 's/^/- /g'

