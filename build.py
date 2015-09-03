import jinja2
import os 
import sys
from bs4 import BeautifulSoup
import csv
import shutil
import dbm
import yaml
import coffeescript
import jinja2_highlight
import collections
import datetime
import re


class NoConfigFileFound(Exception):
	pass


BlogPost = collections.namedtuple('BlogPost', ['title', 'date', 'author', 'content', 'tags', 'meta', 'file'])


try:
	import sass
except:
	print('Please install libsass via pip.')
	sys.exit(0)

# Import Liftpass config 
BasePath = os.path.abspath('../')
sys.path.append(BasePath)


contentDir = 'content/'
outputDir = 'build/'
dataDir = 'data/'
staticDir = 'static/'
blogDir = 'blog/'
templateDir = 'templates/'


class Build:

	def __init__(self, cache=True):
		self.globalData = {}
		self.env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'), extensions=[jinja2_highlight.HighlightExtension])
		self.env.globals = self.globalData
		
		if cache:
			self.cache = dbm.open('.cache', 'c')
		else:
			self.cache = dbm.open('.cache', 'n')

		self.pages = []

	def __del__(self):
		self.cache.close()


	def buildAll(self):
		self.loadData()
		self.renderContent()
		self.compileStatic()

		if self.config.get('sitemap', True):
			self.createSitemap()

	# --------------------------------------------------------------------------
	# 1) Load data 
	# --------------------------------------------------------------------------
	def loadData(self):

		# Load config file
		try:
			self.config = yaml.safe_load(open(os.path.join(dataDir, 'config.yml'), 'r'))
			self.globalData['config'] = self.config
		except:
			raise NoConfigFileFound()

		# Load static data files
		for data in os.listdir(dataDir):
			name = data[0: data.find('.')]
			print('Loading:', name)

			if data.endswith('.csv'):
				self.globalData[name] = list(csv.reader(open(os.path.join(dataDir, data), 'r')))
			elif data.endswith('.yml'):
				self.globalData[name] = yaml.safe_load(open(os.path.join(dataDir, data), 'r'))

		# Load blog posts if any
		self.globalData['blog'] = []
		for postfile in sorted(os.listdir(blogDir)):
			content = open(os.path.join(blogDir, postfile), 'r').read()
			
			head = [m.start() for m in re.finditer('---', content)]
			meta = {}

			# Check if post has front matter
			if len(head)>=2:
				meta = yaml.safe_load(content[head[0]:head[1]])
				content = content[head[1]+3:].strip()

			parts = postfile[0:postfile.rfind('.')].split('-')
			date = datetime.date(year=int(parts[0]), month=int(parts[1]), day=int(parts[2]))
			title = meta.get('title', ' '.join(parts[3:]))
			tags = meta.get('tags', [])
			author = meta.get('author', None)

			self.globalData['blog'].append(BlogPost(title=title, date=date, content=content, tags=tags, author=author, meta=meta, file=postfile))



		self.globalData['created'] = datetime.datetime.now()


	# --------------------------------------------------------------------------
	# 2) Render content 
	# --------------------------------------------------------------------------
	def renderContent(self):
		for directory, nextDir, files in os.walk(contentDir):
			
			currentDir = directory
			currentDir = currentDir.replace(contentDir, outputDir, 1)
			
			if os.path.exists(currentDir) == False:
				print(currentDir)
				os.mkdir(currentDir)

			for content in files:
				if content.endswith('.html') == False:
					continue

				print('Processing:', os.path.join(directory, content))

				self.__renderContentPage(directory, currentDir, content, content)
				

		if len(self.globalData['blog']) and os.path.exists(os.path.join(templateDir, 'page.html')):
			for post in self.globalData['blog']:
				self.__renderContentPage(templateDir, outputDir, 'page.html', post.file, {'post': post})


	def __renderContentPage(self, inputDirectory, outputDirectory, inputFile, outputFile, context = {}):
		# Open page
		data = open(os.path.join(inputDirectory, inputFile), 'r').read()
		
		# Render page 
		template = self.env.from_string(data)

		context['page'] = os.path.join(inputDirectory, inputFile)
		
		data = template.render(context)

		# Make it pretty
		data = BeautifulSoup(data).prettify()
		# Ugly hack to remove trailing spaces from the code tag
		data = re.sub('\s+</code>', '</code>', data)

		# Save
		filename = os.path.join(outputDirectory, outputFile)
		open(filename, 'w+').write(data)

		self.pages.append(filename[filename.find('/')+1:])


	# --------------------------------------------------------------------------
	# 3) Compile static data
	# --------------------------------------------------------------------------
	def compileStatic(self):	
		for directory, nextDir, files in os.walk(staticDir):

			# Skip hidden directories
			if '/.' in directory:
				continue

			currentDir = os.path.join(outputDir, directory)
			
			if os.path.exists(currentDir) == False:
				os.mkdir(currentDir)

			for file in files:
				# Skip hidden files
				if file[0] == '.':
					continue

				source = os.path.join(directory, file)
				
				if file.endswith('.sass'):
					name = file
					name = name.replace('.sass', '.css')
					destination = os.path.join(currentDir, name)
					if self.shouldCompile(source, destination):
						print('Compiling:', source)
						data = sass.compile(string=open(source, 'r').read())
						open(destination, 'w+').write(data)
				elif file.endswith('.coffee'):
					name = file.replace('.coffee', '.js')
					destination = os.path.join(currentDir, name)
					if self.shouldCompile(source, destination):
						print('Compiling:', source)
						data = coffeescript.compile(open(source, 'r').read())
						open(destination, 'w+').write(data)
				else:
					destination = os.path.join(currentDir, file)
					if self.shouldCompile(source, destination):
						print('Copying:', source)
						shutil.copy(source, destination)

	def shouldCompile(self, source, destination):
		res = False
		lastModified = ('%d'%os.stat(source).st_mtime).encode('utf-8')

		if source not in self.cache or os.path.exists(destination) == False:
			res = True
		else:
			res = self.cache[source] != lastModified

		self.cache[source] = lastModified

		return res

	def createSitemap(self):
		template = """
			<?xml version="1.0" encoding="UTF-8"?>
	 		<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
	 			{% for page in pages %}
				<url>
					<loc>{{config.site.url}}/{{page}}</loc>
					<lastmod>{{date}}</lastmod>
					<changefreq>daily</changefreq>
					<priority>0.8</priority>
				</url>
				{% endfor %}
			</urlset>
		"""

		template = self.env.from_string(template)
		
		context = {
			'pages': self.pages,
			'date': datetime.datetime.now().date().strftime('%Y-%m-%d')
		}
		
		data = template.render(pages=self.pages)

		# Save
		filename = os.path.join(outputDir, 'sitemap.xml')
		open(filename, 'w+').write(data)



if __name__ == '__main__':
	
	if len(sys.argv) == 1:
		Build().buildAll()
	else:
		cache = not('--force' in sys.argv)
		Build(cache=cache).buildAll()
