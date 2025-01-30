# adapted from https://forums.fast.ai/t/jupyter-notebook-enhancements-tips-and-tricks/17064/39
# and https://discourse.jupyter.org/t/how-to-get-kernel-state-from-running-local-jupyter-notebook/15028/6

import os
import requests
import ipykernel
from jupyter_server import serverapp

import urllib, json, ipykernel

from nbconvert import WebPDFExporter

import nbformat
import re
import tempfile
import subprocess
import time
import json
import shlex
from IPython.core.magic import register_line_magic
import argparse

from IPython.display import HTML, Markdown
import warnings
warnings.filterwarnings("ignore")

# install chromium if necessary
import os

try:
    ex = WebPDFExporter()
    ex.run_playwright('')
except:
    os.system('playwright install chromium')
    
    
def get_notebook_path():
    """Returns the absolute path of the Notebook or None if it cannot be determined
    NOTE: works only when the security is token-based or there is also no password
    """
    connection_file = os.path.basename(ipykernel.get_connection_file())
    kernel_id = connection_file.split('-', 1)[1].split('.')[0]

    headers = {'Authorization': f'token {os.environ["JUPYTERHUB_API_TOKEN"]}'}
    
    for srv in serverapp.list_running_servers():
        result = requests.get(srv['url'] + 'api/sessions', headers=headers)
        if result.status_code == 200:
            sessions = result.json()
            for sess in sessions:
                if sess['kernel']['id'] == kernel_id:
                    return os.path.join(srv['root_dir'], sess['path'])
        else:
            print(f"Error: {result.status_code} - {result.text}")
    return None




def pdf_from_html(pdf=None, verbose=False):
    """Export the current notebook as a PDF.
    pdf is the name of the PDF to export.
    """
    if verbose:
        print("PDF via notebook_to_pdf")

    fname = get_notebook_path() # absolute path to notebook
    root, fn = os.path.split(fname)
   
    
    p = fname.replace(os.environ['HOME'] + '/', '')
    url =  ('https://jupyterhub-dev.cheme.cmu.edu' + 
             os.environ['JUPYTERHUB_SERVICE_PREFIX'] +
            'lab/tree/' + p)
    
    md = nbformat.notebooknode.from_dict({'cell_type': 'markdown',
                                          'metadata': {},
                                          'source': f'Generated at {time.asctime()}. \n\n Source at [{url}]({url}).'})
        
    with open(fname) as f:
        ipynb = f.read()

    exporter = WebPDFExporter()

    nb = nbformat.reads(ipynb, as_version=4)
    
    # One problem with this package is it doesn't show local images because the html is generated in a temp directory.
    # Here we try to use absolute paths.
    # Replace local paths with full paths
    # From https://github.com/betatim/notebook-as-pdf/issues/18
    RE_local_Images = re.compile(r"!\[(.*)\]\((?!https?://|[A-Z]:\\|/|~/)(.*?)( (\"|').*(\"|'))?\)")

    for cell in nb['cells']:
        if not cell['cell_type'] == 'markdown':
            continue

        offset = 0
        
        for match in RE_local_Images.finditer(cell['source']):
            path = match.group(2)
            fullpath = (os.path.realpath(os.path.join(root, path))).replace(' ', '%20')
            cell['source'] = cell['source'][:match.start(2)+offset] + fullpath + cell['source'][match.end(2)+offset:]
            offset += len(fullpath)-(match.end(2)-match.start(2))                
    
    # insert header    
    nb['cells'].insert(0, md)
    body, resources = exporter.from_notebook_node(nb)
    
    base, ext = os.path.splitext(fname)
    pdf = base + '.pdf'
    with open(pdf, 'wb') as f:
        f.write(body)

    rpath = os.path.relpath(pdf, os.getcwd())
    
    display(Markdown(f'[Open {rpath}]({rpath})'))
            
    html = HTML(f'<a href="{rpath}" download="{os.path.split(rpath)[-1]}">download {rpath}</a>')
    display(html)


            
def pdf(line=""):
    """Line magic to export a notebook to PDF.
    """
    args = shlex.split(line)

    if args and args[-1].endswith(".pdf"):
        pdf = args[-1]
    else:
        pdf = None

    verbose = "-v" in args

    pdf_from_html(pdf, verbose)
    
try:
    pdf = register_line_magic(pdf)
except:
    pass


###################### SEARCH


import chromadb
import os
import glob
from tqdm import tqdm

from nbconvert import MarkdownExporter

def notebook_to_markdown(notebook_path):
    # Load the notebook
    with open(notebook_path, 'r', encoding='utf-8') as f:
        notebook = nbformat.read(f, as_version=4)
    
    # Create a Markdown exporter
    markdown_exporter = MarkdownExporter()
    
    # Convert the notebook to a markdown string
    markdown_string, _ = markdown_exporter.from_notebook_node(notebook)
    
    return markdown_string

dbfile = os.path.expanduser('~/db.chromadb')
collection_name = 'ipynb'

if not os.path.exists(dbfile):
    db = chromadb.PersistentClient(path=dbfile)
    if collection_name in db.list_collections():
        db.delete_collection(collection_name)

    collection = db.get_or_create_collection(collection_name)
    print('Indexing files. It should not take long, and it should only happen once.')
    root = os.path.expanduser('~/s25-06623')
    pattern = os.path.expanduser('~/s25-06623/**/*.ipynb')
    for fullpath in tqdm(glob.glob(pattern, recursive=True)):
        if 'assignment' in fullpath:
            continue

        mdcounter, codecounter = 0, 0
        with open(fullpath) as f:
            ipynb = json.loads(f.read())
            for cell in ipynb['cells']:
                if cell["cell_type"] == "markdown":
                    text = ''.join(cell['source'])
                    path = os.path.relpath(fullpath, start=root)
                    url = f'[{path} :markdown: {mdcounter}](https://jh-01.cheme.cmu.edu/hub/user-redirect/git-pull?repo=https%3A//github.com/jkitchin/s25-06623&urlpath=lab/tree/s25-06623/{path}&branch=main)'
                    # markdown_string = notebook_to_markdown(fullpath)
                    collection.add(documents=[text], ids=[url])
                    mdcounter += 1
                elif cell["cell_type"] == "code":
                    text = ''.join(cell['source'])
                    path = os.path.relpath(fullpath, start=root)
                    url = f'[{path} :code: {codecounter}](https://jh-01.cheme.cmu.edu/hub/user-redirect/git-pull?repo=https%3A//github.com/jkitchin/s25-06623&urlpath=lab/tree/s25-06623/{path}&branch=main)'
                    # markdown_string = notebook_to_markdown(fullpath)
                    collection.add(documents=[text], ids=[url])
                    codecounter += 1
else:
    db = chromadb.PersistentClient(path=dbfile)
    collection = db.get_or_create_collection(collection_name)


from IPython.core.magic import register_cell_magic
from IPython.display import HTML


def search(line, cell):
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', type=int, default=3, help='Number of documents to repeat')
    args = parser.parse_args(line.split())
    
    prompt = cell
    results = collection.query(query_texts=[prompt], n_results=args.n)

    print('The closest notebooks are:')
    for i, (url, doc) in enumerate(zip(results['ids'][0], results['documents'][0]), 1):
        display(Markdown(f'{i}. ' + url))
        if ':markdown:' in url:
            display(Markdown(doc))
        elif ':code:' in url:
            display(Markdown(f'```python\n{doc}\n```'))
            
try:
    search = register_cell_magic(search)
except:
    pass


# Update environment
import os
if not os.path.exists(os.path.expanduser('~/solutions')):
    os.symlink('/usr/local/share/s25-06623',
               os.path.expanduser('~/solutions'), target_is_directory=True)
    
